# -*- coding: utf-8 -*-

import json
import hashlib
import logging
from datetime import datetime

import mkdocs
import elasticsearch
import elasticsearch.helpers

# Use cleaning functions
from mkdocs.contrib.search.search_index import SearchIndex

log = logging.getLogger('mkdocs.elasticsearch')

INDEX_MAPPING = {
    'index_patterns': [],
    'mappings': {
        'document': {
            'properties': {
                'parent_document': {
                    'type': 'join',
                    'relations': {
                        'full_doc': 'section'
                    }
                },
                'text': {'type': 'text'},
                'location': {'type': 'keyword'},
                'title': {'type': 'text'},
            }
        }
    },
    'settings': {
        'number_of_shards': 1,
        'auto_expand_replicas': '0-3', # Reliability over performance
        # 'analysis': {
        #     'analyzer': {
        #         'default': {
        #             'type': 'custom',
        #             'tokenizer': 'standard',
        #             'filter': ['lowercase', 'mySnowball']
        #         },
        #         'default_search': {
        #             'type': 'custom',
        #             'tokenizer': 'standard',
        #             'filter': ['standard', 'lowercase', 'mySnowball']
        #         }
        #     },
        #     'filter': {
        #         'mySnowball': {
        #             'type': 'snowball',
        #             'language': 'English'
        #         }
        #     }
        # }
    }
}

class ElasticsearchPlugin(mkdocs.contrib.search.SearchPlugin):
    config_scheme = (
        ('es_host', mkdocs.config.config_options.URL(required=True)),
        ('es_index', mkdocs.config.config_options.Type(mkdocs.utils.string_types, default='mkdocs')),
    )

    def on_pre_build(self, config, **kwargs):
        if 'dirty' in kwargs and kwargs['dirty']:
            return

        super(ElasticsearchPlugin, self).on_pre_build(config, **kwargs)
        self.es_client = elasticsearch.Elasticsearch(self.config['es_host'])
        log.info(
            'Connecting to elasticsearch at %s [%s]',
            self.config['es_host'],
            self.config['es_index'],
        )
        if not self.es_client.indices.exists_template(self.config['es_index']):
            log.info("Elastic index template %s doesn't exist, creating...", self.config['es_index'])
            INDEX_MAPPING['index_patterns'].append('%s-*' % self.config['es_index'])
            self.es_client.indices.put_template(self.config['es_index'], INDEX_MAPPING)

        self.build_index = '%s-%s' % (
            self.config['es_index'],
            datetime.now().strftime('%Y%m%d%H%M%S')
        )

        log.info('Creating new index %s', self.build_index)
        self.es_client.indices.create(index=self.build_index)

        if not self.es_client.indices.exists_alias(self.config['es_index']):
            log.info("Elastic index alias %s doesn't exist, creating...", self.config['es_index'])
            self.es_client.indices.put_alias(self.build_index, self.config['es_index'])

    def on_post_build(self, config, **kwargs):
        if 'dirty' in kwargs and kwargs['dirty']:
            log.debug("Dirty build, skip rebuilding search index")
            return

        try:
            log.info('Indexing parent documents')
            log.debug(list(self._get_es_parents()))
            elasticsearch.helpers.bulk(self.es_client, self._get_es_parents())
            log.info('Indexing children documents')
            log.debug(list(self._get_es_children()))
            elasticsearch.helpers.bulk(self.es_client, self._get_es_children())

            body = {"actions": [{"remove": {"index": "{}-*".format(self.config['es_index']), "alias": self.config['es_index']}},
                            {"add": {"index": self.build_index, "alias": self.config['es_index']}}]}
            self.es_client.indices.update_aliases(body)
        except Exception as e:
            log.exception('Failed elastic build')

    def _base_es_document(self, doc):
        return {
            '_op_type': 'index',
            '_type': 'document',
            '_index': self.build_index,
            '_id': hashlib.md5(doc['location']).hexdigest(),
            '_routing': 1, # Valid as there is only 1 shard
            '_source': {
                'location': doc['location'],
                'title': doc['title'],
                'text': doc['text'],
            }
        }

    def _get_es_parents(self):
        for doc in self.search_index._entries:
            es_doc = self._base_es_document(doc)
            if '#' not in doc['location']:
                es_doc['_source']['parent_document'] = 'full_doc'
                yield es_doc

    def _get_es_children(self):
        for doc in self.search_index._entries:
            es_doc = self._base_es_document(doc)
            if '#' in doc['location']:
                es_doc['_source']['parent_document'] = {
                    'name': 'section',
                    'parent': hashlib.md5(doc['location'].split('#')[0]).hexdigest()
                }
                yield es_doc

# -*- coding: utf-8 -*-

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
        'properties': {
            'parent_document': {
                'type': 'join',
                'relations': {
                    'full_doc': 'section'
                }
            },
            'text': {
                'type': 'text',
                # 'analyzer': 'mkdocs_ngram_analizer'
            },
            'location': {
                'type': 'text',
                'analyzer': 'mkdocs_location_analizer'
            },
            'title': {
                'type': 'text',
                # 'analyzer': 'mkdocs_ngram_analizer'
            },
        }
    },
    'settings': {
        'number_of_shards': 1,
        'auto_expand_replicas': '0-3', # Reliability over performance
        'analysis': {
            'analyzer': {
                'mkdocs_ngram_analizer': {
                    'tokenizer': 'mkdocs_ngram',
                },
                'mkdocs_location_analizer': {
                    'tokenizer': 'mkdocs_location',
                }
            },
            'tokenizer': {
                'mkdocs_ngram': {
                    'type': 'ngram',
                    'min_ngram': 3,
                    'max_ngram': 10,
                    'token_chars': ['letter', 'digit']
                },
                'mkdocs_location': {
                    'type': 'pattern',
                    'token_chars': '[/#]'
                }
            }
        }
    }
}

class ElasticsearchPlugin(mkdocs.contrib.search.SearchPlugin):
    config_scheme = (
        ('es_host', mkdocs.config.config_options.URL(required=True)),
        ('es_index', mkdocs.config.config_options.Type(str, default='mkdocs')),
    )

    def on_pre_build(self, config, **kwargs):
        if 'dirty' in kwargs and kwargs['dirty']:
            return

        super(ElasticsearchPlugin, self).on_pre_build(config, **kwargs)

    def on_post_build(self, config, **kwargs):
        if 'dirty' in kwargs and kwargs['dirty']:
            log.debug("Dirty build, skip rebuilding search index")
            return

        try:
            self.es_client = elasticsearch.Elasticsearch(self.config['es_host'], timeout=120)
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

            log.info('Indexing parent documents')
            log.debug(list(self._get_es_parents()))
            elasticsearch.helpers.bulk(self.es_client, self._get_es_parents())
            log.info('Indexing children documents')
            log.debug(list(self._get_es_children()))
            elasticsearch.helpers.bulk(self.es_client, self._get_es_children())

            body = {"actions": [{"remove": {"index": "{}-*".format(self.config['es_index']), "alias": self.config['es_index']}},
                            {"add": {"index": self.build_index, "alias": self.config['es_index']}}]}
            self.es_client.indices.update_aliases(body)
            mkdocs_indexes = self.es_client.indices.get("{}-*".format(self.config['es_index']))
            old_indices = [index for index in mkdocs_indexes if index != self.build_index]
            if len(old_indices) > 0:
                self.es_client.indices.delete(old_indices)
        except:
            log.exception('Failed elastic build')

    def _base_es_document(self, doc):
        return {
            '_op_type': 'index',
            '_index': self.build_index,
            '_id': hashlib.md5(doc['location'].encode('utf-8')).hexdigest(),
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
                    'parent': hashlib.md5(doc['location'].split('#')[0].encode('utf-8')).hexdigest()
                }
                yield es_doc

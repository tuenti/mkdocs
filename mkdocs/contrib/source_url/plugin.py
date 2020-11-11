import os

from mkdocs.plugins import BasePlugin
from mkdocs.config import config_options

from mkdocs.contrib.source_url.utils import convert_path_to_source_url


class SourceUrlPlugin(BasePlugin):

    config_scheme = (
        ('repos_file', config_options.Type(str)),
        ('repos_prefix', config_options.Type(str, default="")),
        ('default_url_template', config_options.Type(str, default="")),
        ('github_url_template', config_options.Type(str, default="")),
    )

    def on_config(self, config, **kwargs):
        self.config["repos_info"] = config_options.SourceCodeLink.parse_repos_info(
            self.config["repos_file"]
        )
        return config

    def on_pre_page(self, page, **kwargs):
        source_url = convert_path_to_source_url(
            page.file.src_path,
            repos_prefix=self.config["repos_prefix"],
            repos_info=self.config["repos_info"],
            default_url_template=self.config["default_url_template"],
            github_url_template=self.config["github_url_template"],
        )
        page.source_url = source_url
        return page

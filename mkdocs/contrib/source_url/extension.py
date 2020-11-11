import os

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from markdown.util import AMP_SUBSTITUTE

from mkdocs.contrib.source_url.utils import convert_path_to_source_url
from mkdocs.utils import is_image_file, is_markdown_file, urlparse


class SourceCodeLinkTreeprocessor(Treeprocessor):
    def __init__(self, file, config):
        self.file = file
        self.config = config

    def run(self, root):
        """
        Convert source code URLs into links to external code browser
        """
        for element in root.iter():
            if element.tag == 'a':
                key = 'href'
            else:
                continue

            url = element.get(key)
            new_url = self.path_to_url(url)
            element.set(key, new_url)

        return root

    def path_to_url(self, url):
        scheme, netloc, path, params, query, fragment = urlparse(url)

        if scheme or netloc or not path or AMP_SUBSTITUTE in url or '.' not in os.path.split(path)[-1]:
            # Ignore URLs unless they are a relative link to a source file.
            # AMP_SUBSTITUTE is used internally by Markdown only for email.
            # No '.' in the last part of a path indicates path does not point to a file.
            return url

        # Determine the filepath of the target.
        target_path = os.path.join(os.path.dirname(self.file.src_path), path)
        target_path = os.path.normpath(target_path).lstrip(os.sep)

        if not self.is_source_code_link(target_path):
            return url

        source_url = convert_path_to_source_url(
            target_path,
            repos_prefix=self.config['repos_prefix'],
            repos_info=self.config['repos_info'],
            default_url_template=self.config['default_url_template'],
            github_url_template=self.config['github_url_template'],
        )

        return source_url or url

    def is_source_code_link(self, path):
        return not is_markdown_file(path) and not is_image_file(path) and path.startswith(self.config['repos_prefix'])


class SourceCodeLinkExtension(Extension):
    """
    The Extension class is what we pass to markdown, it then
    registers the Treeprocessor.
    """

    def __init__(self, file, config):
        self.file = file
        self.config = config

    def extendMarkdown(self, md, md_globals):
        source_code_link = SourceCodeLinkTreeprocessor(self.file, self.config)
        md.treeprocessors.add("sourcecodelink", source_code_link, "_end")

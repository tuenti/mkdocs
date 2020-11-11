import os.path


def get_repo_info_for_path(repos_info, path):
    longest_match = None
    for repo_info in repos_info:
        if is_github_repo(repo_info.url):
            if repo_info.dir == path.split("/")[0]:
                return repo_info
        else:
            if path.startswith(repo_info.dir):
                if not longest_match or len(repo_info.dir) > len(longest_match.dir):
                    longest_match = repo_info

    return longest_match


def is_github_repo(repo_url):
    return "github.com" in repo_url


def remove_prefix(value, prefix):
    if value.startswith(prefix):
        return value[len(prefix):]
    return value


def convert_path_to_source_url(
    path,
    *,
    repos_prefix,
    repos_info,
    default_url_template,
    github_url_template=None
):
    target_path = remove_prefix(path.lstrip(os.sep), repos_prefix).lstrip(os.sep)
    repo_info = get_repo_info_for_path(repos_info, target_path)
    if not repo_info:
        return None
    target_path = remove_prefix(target_path, repo_info.dir).lstrip(os.sep)

    template = default_url_template
    if is_github_repo(repo_info.url):
        template = github_url_template or template

    source_url = template.format(
        repo_url=repo_info.url,
        branch="master",
        path=target_path,
        repo_id=repo_info.id,
    )
    return source_url

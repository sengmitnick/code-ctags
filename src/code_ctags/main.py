import os
import sys
import git
import configargparse
from pathlib import Path, PurePosixPath

from .repomap import RepoMap


def find_py_files(directory: str):
    if not os.path.isdir(directory):
        return [directory]

    py_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            py_files.append(os.path.join(root, file))

    return py_files


def get_tracked_files(repo: git.Repo, root_dir: str):
    try:
        commit = repo.head.commit
    except ValueError:
        commit = None

    files = []
    if commit:
        for blob in commit.tree.traverse():
            if blob.type == "blob":  # blob is a file
                files.append(blob.path)

    # Add staged files
    index = repo.index
    staged_files = [path for path, _ in index.entries.keys()]

    files.extend(staged_files)

    # convert to appropriate os.sep, since git always normalizes to /
    res = set(
        str(Path(PurePosixPath((Path(root_dir) / path).relative_to(root_dir))))
        for path in files
    )

    return res


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    root_dir = os.getcwd()

    parser = configargparse.ArgumentParser(
        description="通过 ctags 可以把当前目前下的所有文件的函数、类、变量等标签都输出到终端。",
    )

    ##########
    core_group = parser.add_argument_group("Main")
    core_group.add_argument(
        "--ctags_full",
        metavar="ctags_full",
        default=True,
        help=f"ctags输出是否全部输出不做对比 (default: False)",
    )

    args = parser.parse_args(argv)

    encoding = "utf-8"
    chat_fnames = []
    other_fnames = []

    try:
        repo = git.Repo(root_dir)
        other_fnames = get_tracked_files(repo, root_dir)
    except git.exc.InvalidGitRepositoryError:
        other_fnames += find_py_files(root_dir)

    repo_map = RepoMap(encoding, root_dir, ctags_full=args.ctags_full)

    repo_content = repo_map.get_repo_map(chat_fnames, other_fnames)
    print(repo_content)


if __name__ == "__main__":
    status = main()
    sys.exit(status)

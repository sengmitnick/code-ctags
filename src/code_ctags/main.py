import os
import sys
import configargparse

from .repomap import RepoMap


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
    core_group.add_argument(
        "--fnames",
        nargs="+",
        metavar="fnames",
        required=True,
        default=[],
        help=f"文件列表",
    )

    args = parser.parse_args(argv)

    encoding = "utf-8"
    chat_fnames = []
    other_fnames = args.fnames

    repo_map = RepoMap(encoding, root_dir, ctags_full=args.ctags_full)

    repo_content = repo_map.get_repo_map(chat_fnames, other_fnames)
    print(repo_content)


if __name__ == "__main__":
    status = main()
    sys.exit(status)

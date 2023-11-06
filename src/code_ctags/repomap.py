import json
import os
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound
from tqdm import tqdm


def to_tree(tags):
    if not tags:
        return ""

    tags = sorted(tags)

    output = ""
    last = [None] * len(tags[0])
    tab = "\t"
    for tag in tags:
        tag = list(tag)

        for i in range(len(last) + 1):
            if i == len(last):
                break
            if last[i] != tag[i]:
                break

        num_common = i

        indent = tab * num_common
        rest = tag[num_common:]
        for item in rest:
            output += indent + item + "\n"
            indent += tab
        last = tag

    return output


def fname_to_components(fname, with_colon):
    path_components = fname.split(os.sep)
    res = [pc + os.sep for pc in path_components[:-1]]
    if with_colon:
        res.append(path_components[-1] + ":")
    else:
        res.append(path_components[-1])
    return res


class RepoMap:
    CACHE_VERSION = 1
    ctags_cmd = [
        "ctags",
        "--fields=+S",
        "--extras=-F",
        "--output-format=json",
        "--output-encoding=utf-8",
    ]

    ctags_disabled_reason = "ctags not initialized"

    cache_missing = False

    def __init__(
        self,
        encoding="utf-8",
        root: str = None,
        ctags_full=False,
        repo_content_prefix: str = None,
        verbose=False,
    ):
        self.ctags_full = ctags_full
        self.encoding = encoding
        self.verbose = verbose

        if not root:
            root = os.getcwd()
        self.root = root

        self.has_ctags = self.check_for_ctags()
        self.use_ctags = True
        self.repo_content_prefix = repo_content_prefix

    def get_repo_map(self, chat_files, other_files):
        res = self.choose_files_listing(chat_files, other_files)
        if not res:
            return

        files_listing, ctags_msg = res

        if chat_files:
            other = "other "
        else:
            other = ""

        if self.repo_content_prefix:
            repo_content = self.repo_content_prefix.format(
                other=other,
                ctags_msg=ctags_msg,
            )
        else:
            repo_content = ""

        repo_content += files_listing

        return repo_content

    def choose_files_listing(self, chat_files, other_files):

        if not other_files:
            return

        if self.use_ctags:
            files_listing = self.get_ranked_tags_map(chat_files, other_files)
            if files_listing:
                ctags_msg = " with selected ctags info"
                return files_listing, ctags_msg

        files_listing = self.get_simple_files_map(other_files)
        ctags_msg = ""
        return files_listing, ctags_msg

    def get_simple_files_map(self, other_files):
        fnames = []
        for fname in other_files:
            fname = self.get_rel_fname(fname)
            fname = fname_to_components(fname, False)
            fnames.append(fname)

        return to_tree(fnames)

    def get_rel_fname(self, fname):
        return os.path.relpath(fname, self.root)

    def run_ctags(self, filename):
        # Check if the file is in the cache and if the modification time has not changed
        file_mtime = self.get_mtime(filename)
        if file_mtime is None:
            return []

        cmd = self.ctags_cmd + [
            f"--input-encoding={self.encoding}",
            filename,
        ]
        output = subprocess.check_output(
            cmd, stderr=subprocess.PIPE).decode("utf-8")
        output_lines = output.splitlines()

        data = []
        for line in output_lines:
            try:
                data.append(json.loads(line))
            except json.decoder.JSONDecodeError as err:
                print(f"[run_ctags]Error parsing ctags output: {err}")

        return data

    def check_for_ctags(self):
        try:
            executable = self.ctags_cmd[0]
            cmd = [executable, "--version"]
            output = subprocess.check_output(
                cmd, stderr=subprocess.PIPE).decode("utf-8")
            output = output.lower()

            cmd = " ".join(cmd)

            if "universal ctags" not in output:
                self.ctags_disabled_reason = f"{cmd} does not claim to be universal ctags"
                return
            if "+json" not in output:
                self.ctags_disabled_reason = f"{cmd} does not list +json support"
                return

            with tempfile.TemporaryDirectory() as tempdir:
                hello_py = os.path.join(tempdir, "hello.py")
                with open(hello_py, "w", encoding="utf-8") as f:
                    f.write("def hello():\n    print('Hello, world!')\n")
                self.run_ctags(hello_py)
        except FileNotFoundError:
            self.ctags_disabled_reason = f"{executable} executable not found"
            return
        except Exception as err:
            self.ctags_disabled_reason = f"error running universal-ctags: {err}"
            return

        return True

    def get_mtime(self, fname):
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            print(f"[get_mtime]File not found error: {fname}")

    def get_name_identifiers(self, fname, uniq=True):
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return set()

        idents = self.get_name_identifiers_uncached(fname)

        if uniq:
            idents = set(idents)
        return idents

    def read_text(self, filename):
        try:
            with open(str(filename), "r", encoding=self.encoding) as f:
                return f.read()
        except FileNotFoundError:
            # print(f"[read_text]{filename}: file not found error")
            return
        except UnicodeError as e:
            # print(f"[read_text]{filename}: {e}")
            return

    def get_name_identifiers_uncached(self, fname):
        content = self.read_text(fname)
        if content is None:
            return list()

        try:
            lexer = guess_lexer_for_filename(fname, content)
        except ClassNotFound:
            return list()

        # lexer.get_tokens_unprocessed() returns (char position in file, token type, token string)
        tokens = list(lexer.get_tokens_unprocessed(content))
        res = [token[2] for token in tokens if token[1] in Token.Name]
        return res

    def get_ranked_tags(self, chat_fnames, other_fnames):
        defines = defaultdict(set)
        references = defaultdict(list)
        definitions = defaultdict(set)

        personalization = dict()

        fnames = set(chat_fnames).union(set(other_fnames))
        chat_rel_fnames = set()

        fnames = sorted(fnames)

        if self.cache_missing:
            fnames = tqdm(fnames)
        self.cache_missing = False

        for fname in fnames:
            if not Path(fname).is_file():
                print(f"[get_ranked_tags]Repo-map can't include {fname}")
                continue

            # dump(fname)
            rel_fname = os.path.relpath(fname, self.root)

            if fname in chat_fnames:
                personalization[rel_fname] = 1.0
                chat_rel_fnames.add(rel_fname)

            data = self.run_ctags(fname)

            for tag in data:
                ident = tag["name"]
                defines[ident].add(rel_fname)

                scope = tag.get("scope")
                kind = tag.get("kind")
                name = tag.get("name")
                signature = tag.get("signature")

                last = name
                if signature:
                    last += " " + signature

                res = [rel_fname]
                if scope:
                    res.append(scope)
                res += [kind, last]

                key = (rel_fname, ident)
                definitions[key].add(tuple(res))
                # definitions[key].add((rel_fname,))

            idents = self.get_name_identifiers(fname, uniq=False)
            for ident in idents:
                # dump("ref", fname, ident)
                references[ident].append(rel_fname)

        idents = set(defines.keys()).intersection(set(references.keys()))

        G = nx.MultiDiGraph()

        for ident in idents:
            definers = defines[ident]
            for referencer, num_refs in Counter(references[ident]).items():
                for definer in definers:
                    if referencer == definer and self.ctags_full is False:
                        continue
                    G.add_edge(referencer, definer,
                               weight=num_refs, ident=ident)

        if personalization:
            pers_args = dict(personalization=personalization,
                             dangling=personalization)
        else:
            pers_args = dict()

        try:
            ranked = nx.pagerank(G, weight="weight", **pers_args)
        except ZeroDivisionError:
            return []

        # distribute the rank from each source node, across all of its out edges
        ranked_definitions = defaultdict(float)
        for src in G.nodes:
            src_rank = ranked[src]
            total_weight = sum(data["weight"] for _src,
                               _dst, data in G.out_edges(src, data=True))
            # dump(src, src_rank, total_weight)
            for _src, dst, data in G.out_edges(src, data=True):
                data["rank"] = src_rank * data["weight"] / total_weight
                ident = data["ident"]
                ranked_definitions[(dst, ident)] += data["rank"]

        ranked_tags = []
        ranked_definitions = sorted(
            ranked_definitions.items(), reverse=True, key=lambda x: x[1])
        for (fname, ident), rank in ranked_definitions:
            if fname in chat_rel_fnames:
                continue
            ranked_tags += list(definitions.get((fname, ident), []))

        rel_other_fnames_without_tags = set(
            os.path.relpath(fname, self.root) for fname in other_fnames
        )

        fnames_already_included = set(rt[0] for rt in ranked_tags)

        top_rank = sorted([(rank, node)
                          for (node, rank) in ranked.items()], reverse=True)
        for rank, fname in top_rank:
            if fname in rel_other_fnames_without_tags:
                rel_other_fnames_without_tags.remove(fname)
            if fname not in fnames_already_included:
                ranked_tags.append((fname,))

        for fname in rel_other_fnames_without_tags:
            ranked_tags.append((fname,))

        return ranked_tags

    def get_ranked_tags_map(self, chat_fnames, other_fnames=None):
        if not other_fnames:
            other_fnames = list()

        ranked_tags = self.get_ranked_tags(chat_fnames, other_fnames)
        num_tags = len(ranked_tags)

        lower_bound = 0
        upper_bound = num_tags
        best_tree = None

        while lower_bound <= upper_bound:
            middle = (lower_bound + upper_bound) // 2
            tree = to_tree(ranked_tags[:middle])
            # dump(middle, num_tokens)
            best_tree = tree
            lower_bound = middle + 1

        return best_tree

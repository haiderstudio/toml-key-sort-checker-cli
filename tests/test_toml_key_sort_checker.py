#!/usr/bin/env python3
"""Tests for toml_key_sort_checker — stdlib unittest only.

Every TOML document in this file is made up for testing.
No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import toml_key_sort_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/toml_key_sort_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text):
    return checker.check_text(text)


class TestKeyOrder(unittest.TestCase):
    def test_sorted_keys_pass(self):
        self.assertEqual(
            findings_of("apple = 1\nbanana = 2\ncherry = 3\n"), [])

    def test_out_of_order_key_fails(self):
        bad = findings_of("zebra = 1\napple = 2\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 2)
        self.assertEqual(bad[0]["key"], "apple")
        self.assertEqual(bad[0]["previous"], "zebra")
        self.assertIn("out of order", bad[0]["reason"])

    def test_multiple_bad_keys_in_document_order(self):
        text = ("zebra = 1\n"
                "apple = 2\n"
                "mango = 3\n"
                "banana = 4\n")
        bad = findings_of(text)
        self.assertEqual([f["line"] for f in bad], [2, 4])

    def test_case_insensitive_order(self):
        self.assertEqual(
            findings_of('Apple = 1\nbanana = 2\nCherry = 3\n'), [])
        bad = findings_of("banana = 1\nApple = 2\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["key"], "Apple")

    def test_equal_keys_do_not_fail(self):
        # A duplicate key is a TOML error, not an order
        # problem — the line pass only checks order.
        self.assertEqual(
            findings_of("apple = 1\napple = 2\n"), [])

    def test_numbers_sort_as_characters(self):
        self.assertEqual(findings_of('"10" = 1\n"2" = 2\n'), [])
        bad = findings_of('"2" = 1\n"10" = 2\n')
        self.assertEqual(len(bad), 1)

    def test_table_header_starts_new_order(self):
        text = ("zebra = 1\n"
                "[server]\n"
                "apple = 2\n"
                "banana = 3\n")
        self.assertEqual(findings_of(text), [])

    def test_out_of_order_inside_table(self):
        text = ("[server]\n"
                "port = 8080\n"
                "host = \"localhost\"\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 3)
        self.assertEqual(bad[0]["key"], "host")

    def test_array_of_tables_starts_new_order(self):
        text = ("[[fruit]]\n"
                "zebra = 1\n"
                "[[fruit]]\n"
                "apple = 2\n")
        self.assertEqual(findings_of(text), [])

    def test_comments_and_blank_lines_ignored(self):
        text = ("# a comment\n"
                "\n"
                "zebra = 1 # trailing comment\n"
                "# another comment\n"
                "apple = 2\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 5)

    def test_comment_with_equals_is_not_a_key(self):
        text = ("# zebra = 1\n"
                "apple = 2\n")
        self.assertEqual(findings_of(text), [])

    def test_hash_inside_string_is_not_a_comment(self):
        text = ('note = "a # b"\n'
                "apple = 2\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["key"], "apple")

    def test_quoted_keys_compared_unquoted(self):
        self.assertEqual(
            findings_of('"alpha" = 1\n"Beta" = 2\n'), [])
        bad = findings_of('"Beta" = 1\n\'alpha\' = 2\n')
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["key"], "alpha")

    def test_dotted_keys_compared_in_full(self):
        self.assertEqual(
            findings_of("a.b = 1\na.c = 2\nb = 3\n"), [])
        bad = findings_of("a.z = 1\na.b = 2\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["key"], "a.b")

    def test_dotted_keys_with_spaces_around_dots(self):
        self.assertEqual(
            findings_of("a . b = 1\na . c = 2\n"), [])
        bad = findings_of("a . z = 1\na . b = 2\n")
        self.assertEqual(len(bad), 1)

    def test_inline_table_sorted_passes(self):
        self.assertEqual(
            findings_of("point = {x = 1, y = 2}\n"), [])

    def test_inline_table_out_of_order_fails(self):
        bad = findings_of("point = {y = 2, x = 1}\n")
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 1)
        self.assertEqual(bad[0]["key"], "x")
        self.assertIn("inline table", bad[0]["reason"])

    def test_nested_inline_table_has_own_order(self):
        text = "outer = {a = {z = 1, b = 2}, c = 3}\n"
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["key"], "b")

    def test_inline_table_string_with_equals_ignored(self):
        text = 'msg = {text = "a = b", when = "now"}\n'
        self.assertEqual(findings_of(text), [])

    def test_multiline_string_lines_not_checked(self):
        text = ('text = """\n'
                "zebra: this is text, not a key\n"
                "apple: so is this\n"
                '"""\n'
                "zebra = 2\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 0)

    def test_multiline_array_lines_not_checked(self):
        text = ("tags = [\n"
                '  "zebra",\n'
                '  "apple",\n'
                "]\n"
                "zebra = 2\n")
        self.assertEqual(findings_of(text), [])

    def test_key_after_multiline_array_checked(self):
        text = ("zebra = [\n"
                '  "a",\n'
                "]\n"
                "apple = 2\n")
        bad = findings_of(text)
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["line"], 4)

    def test_empty_document_passes(self):
        self.assertEqual(findings_of(""), [])

    def test_document_with_only_comments_passes(self):
        self.assertEqual(findings_of("# nothing here\n"), [])

    def test_key_with_no_value_is_not_a_key(self):
        # "orphan" is not valid TOML; the line pass
        # only checks lines that carry a key and "=".
        self.assertEqual(findings_of("orphan\napple = 1\n"), [])


class TestTomlValidation(unittest.TestCase):
    def test_invalid_toml_reported_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "bad.toml", "key = [\n")
            bad, error = checker.check_file(path)
            self.assertEqual(bad, [])
            self.assertIn("not valid TOML", error)

    def test_duplicate_key_reported_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "dup.toml",
                         "apple = 1\napple = 2\n")
            bad, error = checker.check_file(path)
            self.assertEqual(bad, [])
            self.assertIn("not valid TOML", error)

    def test_valid_toml_checked_for_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "ok.toml", "zebra = 1\napple = 2\n")
            bad, error = checker.check_file(path)
            self.assertIsNone(error)
            self.assertEqual(len(bad), 1)


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml",
                         "apple = 1\nbanana = 2\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("every table key is sorted", out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml",
                         "zebra = 1\napple = 2\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 2", out)
            self.assertIn("out of order", out)
            self.assertIn(path, out)

    def test_invalid_toml_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.toml", "key = [\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid TOML", out)

    def test_folder_walk_finds_toml_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.toml", "apple = 1\n")
            write(tmp, "b.toml", "zebra = 1\napple = 2\n")
            write(tmp, "notes.txt", "zebra = 1\napple = 2\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("b.toml", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.toml", "apple = 1\n")
            write(tmp, "sub/b.toml", "zebra = 1\napple = 2\n")
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.toml", "apple = 1\n")
            write(tmp, "b.toml", "zebra = 1\napple = 2\n")
            code, out, err = run_cli([tmp, "--exclude", "b.toml"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.toml", "apple = 1\n")
            write(tmp, ".git/b.toml", "zebra = 1\napple = 2\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "config.txt", "zebra = 1\napple = 2\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("config.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.toml", "apple = 1\n")
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.toml", "zebra = 1\napple = 2\n")
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["line"], 2)
            self.assertEqual(
                data["files"][0]["findings"][0]["key"], "apple")
            self.assertEqual(
                data["files"][0]["findings"][0]["previous"], "zebra")
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input="apple = 1\nbanana = 2\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("every table key is sorted", result.stdout)

    def test_stdin_dirty(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input="zebra = 1\napple = 2\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL <stdin>: line 2", result.stdout)

    def test_stdin_invalid_toml(self):
        result = subprocess.run(
            [sys.executable, str(SRC), "--stdin"],
            input="key = [\n",
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("not valid TOML", result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "config.toml"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no TOML files found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("toml_key_sort_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.toml", b"\xff\xfeapple = 1\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.toml", "zebra = 1\napple = 2\n")
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "a.toml", "apple = 1\n")
            result = subprocess.run(
                [sys.executable, str(SRC), "a.toml"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every table key is sorted", result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "a.toml", "apple = 1\n")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/toml_key_sort_checker.py",
             "examples/good.toml"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/toml_key_sort_checker.py",
             "examples/bad.toml"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/toml_key_sort_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 3 file(s), 2 key(s) out of order "
                      "in 1 file(s).", folder.stdout)
        self.assertIn("Checked 3 file(s), 2 key(s) out of order "
                      "in 1 file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/toml_key_sort_checker.py",
             "examples/edge.toml"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/toml_key_sort_checker.py",
             "--json", "examples/bad.toml"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/tmp/", "/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/toml_key_sort_checker.py",
                       REPO / "tests/test_toml_key_sort_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"toml_key_sort_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/toml_key_sort_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_toml_key_sort_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("toml-validator-cli", readme)
        self.assertIn("yaml-key-sort-checker-cli", readme)
        self.assertIn("requirements-sort-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()

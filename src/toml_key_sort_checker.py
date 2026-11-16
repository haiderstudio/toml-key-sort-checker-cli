#!/usr/bin/env python3
"""Check keys in TOML files are sorted alphabetically.

Run: python3 src/toml_key_sort_checker.py config.toml
     python3 src/toml_key_sort_checker.py project/
     python3 src/toml_key_sort_checker.py --stdin < config.toml

Sorted keys give cleaner diffs and make a
duplicate or misplaced key obvious at a glance —
the same reason requirements files are sorted.
This tool reads the TOML files you point it at,
checks the keys of every table are in
alphabetical order, and reports each key that is
out of order with the file and the line number.
It exits 1 when any key is out of order, so it
can fail a CI run. A file with sorted keys
exits 0.

Order is plain alphabetical order on the key
text, ignoring case — "Apple" sorts before
"banana", and "10" sorts before "2", because
the check compares characters, not numbers.
Keys are compared inside their own table only:
a "[table]" header starts a new order, and an
array-of-tables header "[[table]]" starts one
too, so a key is never compared against a key
from another table. Dotted keys are compared
on their full dotted text — "a.b" sorts before
"a.z" — and keys inside a one-line inline
table are compared inside that table. Comments
and blank lines are ignored, and a key inside
a multi-line string or a multi-line array is
content, not a key, and is never checked.

The file is first checked with the standard
library's tomllib, so a file that is not valid
TOML is reported instead of being order-checked
on broken text. The order check itself reads
the raw lines, because tomllib loses the line
numbers — the two passes agree on what a key
is, and the line pass only ever reports order.

It never rewrites a file, never touches the
network, and reads only the files and folders
you point it at.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
import tomllib
from pathlib import Path

__version__ = "1.0.0"

KEY_PART = r"(?:[A-Za-z0-9_-]+|\"(?:[^\"\\]|\\.)*\"|'(?:[^']*)')"
KEY_RE = re.compile(
    r"^\s*(" + KEY_PART + r"(?:\s*\.\s*" + KEY_PART + r")*)\s*=")
INLINE_KEY_RE = re.compile(
    r"(" + KEY_PART + r"(?:\s*\.\s*" + KEY_PART + r")*)\s*=")
KEY_PART_RE = re.compile(KEY_PART)


def _unquote(part):
    """Remove the quotes from one quoted key part."""
    if len(part) >= 2 and part[0] == '"' and part[-1] == '"':
        return part[1:-1]
    if len(part) >= 2 and part[0] == "'" and part[-1] == "'":
        return part[1:-1]
    return part


def _normalise_key(matched):
    """One dotted key as plain text, quotes removed.

    "a . 'b c'" becomes "a.b c" — the form the
    order check compares, case-insensitively.
    """
    parts = KEY_PART_RE.findall(matched)
    return ".".join(_unquote(part) for part in parts)


def strip_comment(line):
    """Remove a trailing TOML comment: '#' outside quotes."""
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_single:
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "#":
                return line[:i]
        i += 1
    return line


def _scan_value(text):
    """Walk one value's text, quotes ignored.

    Returns (bracket_delta, has_inline_table):
    the net change in [ ] { } depth, and whether
    an inline table opens in it.
    """
    depth = 0
    has_inline = False
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
        elif in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
        else:
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch in "[{":
                depth += 1
                if ch == "{":
                    has_inline = True
            elif ch in "]}":
                depth -= 1
        i += 1
    return depth, has_inline


def _inline_findings(text, line_no):
    """Check key order inside one-line inline tables.

    Returns findings for keys out of order inside
    each { ... } on this one line. A key inside a
    nested inline table starts its own order.
    """
    findings = []
    # One last key per open brace depth.
    last_keys = []
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\":
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "{":
            last_keys.append(None)
            i += 1
            continue
        if ch == "}":
            if last_keys:
                last_keys.pop()
            i += 1
            continue
        if last_keys:
            match = INLINE_KEY_RE.match(text, i)
            if match:
                key = _normalise_key(match.group(1))
                lowered = key.lower()
                previous = last_keys[-1]
                if previous is not None and lowered < previous:
                    findings.append({
                        "line": line_no,
                        "key": key,
                        "previous": previous,
                        "reason": ('key "%s" is out of order inside '
                                   'an inline table — it sorts '
                                   'before "%s"' % (key, previous)),
                    })
                last_keys[-1] = lowered
                i = match.end()
                continue
        i += 1
    return findings


def check_text(text):
    """Check one document's text.

    Returns a list of findings, each {"line": int,
    "key": str or None, "previous": str or None,
    "reason": str}, in document order.
    """
    findings = []
    last_key = None
    in_triple = None
    bracket_depth = 0
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        if in_triple is not None:
            if in_triple in line:
                in_triple = None
            continue
        code = strip_comment(line).rstrip()
        if code.strip() == "":
            continue
        if bracket_depth > 0:
            delta, _inline = _scan_value(code)
            bracket_depth += delta
            continue
        body = code.lstrip(" ")
        if body.startswith("[[") and body.rstrip().endswith("]]"):
            last_key = None
            continue
        if body.startswith("[") and body.rstrip().endswith("]"):
            last_key = None
            continue
        match = KEY_RE.match(code)
        if match is None:
            continue
        key = _normalise_key(match.group(1))
        lowered = key.lower()
        if last_key is not None and lowered < last_key:
            findings.append({
                "line": number,
                "key": key,
                "previous": last_key,
                "reason": ('key "%s" is out of order — it sorts '
                           'before "%s"' % (key, last_key)),
            })
        last_key = lowered
        value = code[match.end():].lstrip()
        for quote in ('"""', "'''"):
            if value.startswith(quote):
                rest = value[len(quote):]
                if quote not in rest:
                    in_triple = quote
                break
        else:
            delta, has_inline = _scan_value(value)
            if delta > 0:
                bracket_depth = delta
            elif has_inline:
                findings.extend(_inline_findings(value, number))
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    try:
        with open(path, "rb") as handle:
            tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        return [], "not valid TOML: %s" % exc
    except OSError as exc:
        return [], str(exc)
    return check_text(text), None


def _is_toml_file(path):
    return Path(path).name.lower().endswith(".toml")


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of TOML files.

    A file given directly is always checked, whatever
    its name. A folder is walked for files ending in
    .toml only, recursively by default. .git folders
    are never walked, and directory links are never
    followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_toml_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one out-of-order key."""
    return ("FAIL %s: line %d %s"
            % (path, finding["line"], finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no TOML files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2, ensure_ascii=False))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d key(s) out of order "
                  "in %d file(s)." % (len(files), findings,
                                      files_with_findings))
        else:
            print("OK — %d file(s) checked, every table key "
                  "is sorted." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one TOML document read from standard input."""
    text = sys.stdin.read()
    error = None
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        error = "not valid TOML: %s" % exc
    if error:
        if as_json:
            print(json.dumps(
                {"files": [{"path": "<stdin>", "findings": [],
                            "error": error}],
                 "checked": 1, "findings": 1},
                indent=2, ensure_ascii=False))
        else:
            print("FAIL <stdin>: %s" % error)
        return 1
    bad = check_text(text)
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2, ensure_ascii=False))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d key(s) out of order "
                  "in 1 file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every table key "
                  "is sorted.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="toml_key_sort_checker",
        description="Check TOML table keys are sorted "
                    "alphabetically, fail CI when one is out "
                    "of order. Report-only: it never edits "
                    "a file.")
    parser.add_argument("paths", nargs="*",
                        help="TOML files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one TOML document from standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one TOML file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())

# toml-key-sort-checker-cli

Check keys in TOML files are sorted alphabetically — fail CI when one is not.

[![CI](https://github.com/haiderstudio/toml-key-sort-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/toml-key-sort-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`toml_key_sort_checker` reads each TOML file,
checks the keys of every table are in
alphabetical order, and reports each key that is
out of order with the file and the line number.
It exits 1 when any key is out of order, so it
can fail a CI run. A file with sorted keys
exits 0.

- Sorted keys give cleaner diffs and make a
  duplicate or misplaced key obvious at a glance
  — the same reason repo #90,
  requirements-sort-checker-cli, exists for
  requirements files and repo #102,
  yaml-key-sort-checker-cli, for YAML.
- Order is plain alphabetical order on the key
  text, ignoring case — "Apple" sorts before
  "banana", and "10" sorts before "2", because
  the check compares characters, not numbers.
- Keys are compared inside their own table only:
  a `[table]` header starts a new order, and an
  array-of-tables header `[[table]]` starts one
  too, so a key is never compared against a key
  from another table. Dotted keys are compared
  on their full dotted text — "a.b" sorts before
  "a.z" — and keys inside a one-line inline table
  are compared inside that table. Comments and
  blank lines are ignored, and a key inside a
  multi-line string or a multi-line array is
  content, not a key, and is never checked.
- The file is first checked with the standard
  library's `tomllib`, so a file that is not
  valid TOML is reported instead of being
  order-checked on broken text. The order check
  itself reads the raw lines, because `tomllib`
  loses the line numbers.
- A file given directly on the command line is
  always checked, whatever its name. A folder is
  walked for files ending in `.toml` only,
  recursively by default (`--no-recursive` stops
  at the top level). `.git` folders are never
  walked, and directory links are never followed.
- `--json` prints the result as JSON, and
  `--stdin` checks one TOML document read from
  standard input.

## Who it is for

Every project with a long TOML config — a
`pyproject.toml`, a Cargo manifest, a tool
config. Nobody sorts keys by hand reliably, and
an unsorted config hides a duplicate or a
misplaced key. This is the gate that keeps the
order honest at the pull request.

## What it does NOT do

- It does not check that the TOML is valid beyond
  reporting a file that does not parse. Full
  validation, required keys, and value types are
  repo #36, toml-validator-cli — it validates
  that TOML parses and checks required keys and
  types, but it does not check key order.
- It does not check key order in YAML or JSON.
  YAML is repo #102, yaml-key-sort-checker-cli —
  TOML is a different file format.
- It does not check the order of the tables
  themselves, only the keys inside each table.
  Keys inside a multi-line inline table are not
  checked — only one-line inline tables are.
- It never rewrites a file, and it never touches
  the network.

## How this differs

- A fresh search of GitHub on Nov 15, 2026 found
  0 results for `"toml-key-sort-checker-cli"` and 0
  results for `toml key sort checker` — a
  completely empty field.
- No rival checks TOML key order.

## Install

```sh
git clone https://github.com/haiderstudio/toml-key-sort-checker-cli.git
cd toml-key-sort-checker-cli
```

There is nothing else to install: Python 3.11 or newer
(`tomllib` is standard library from 3.11), no dependencies.

## Usage

Check one TOML file:

```sh
python3 src/toml_key_sort_checker.py config.toml
```

A file with sorted keys passes:

```sh
$ python3 src/toml_key_sort_checker.py examples/good.toml
OK — 1 file(s) checked, every table key is sorted.
```

A file with keys out of order fails, with the
file and line for each one:

```sh
$ python3 src/toml_key_sort_checker.py examples/bad.toml
FAIL examples/bad.toml: line 4 key "apple" is out of order — it sorts before "zebra"
FAIL examples/bad.toml: line 8 key "host" is out of order — it sorts before "port"
Checked 1 file(s), 2 key(s) out of order in 1 file(s).
```

Check a whole folder (`.toml` files only):

```sh
$ python3 src/toml_key_sort_checker.py examples/
FAIL examples/bad.toml: line 4 key "apple" is out of order — it sorts before "zebra"
FAIL examples/bad.toml: line 8 key "host" is out of order — it sorts before "port"
Checked 3 file(s), 2 key(s) out of order in 1 file(s).
```

Check one document from standard input:

```sh
$ printf 'zebra = 1\napple = 2\n' | python3 src/toml_key_sort_checker.py --stdin
FAIL <stdin>: line 2 key "apple" is out of order — it sorts before "zebra"
Checked 1 file(s), 1 key(s) out of order in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/toml_key_sort_checker.py --json examples/bad.toml
{
  "files": [
    {
      "path": "examples/bad.toml",
      "findings": [
        {
          "line": 4,
          "key": "apple",
          "previous": "zebra",
          "reason": "key \"apple\" is out of order — it sorts before \"zebra\""
        },
        {
          "line": 8,
          "key": "host",
          "previous": "port",
          "reason": "key \"host\" is out of order — it sorts before \"port\""
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 2
}
```

Exit codes: 0 when every table key is sorted, 1
when any key is out of order or a file cannot be
read or parsed, 2 for a usage error (a missing
path, a bad flag, or no TOML files found).

## Examples

Case does not matter, quoted keys count by their
plain text, and dotted keys count on their full
dotted text — `examples/edge.toml` has all of
them, plus a multi-line string and a multi-line
array whose lines are not keys, and it passes:

```sh
$ python3 src/toml_key_sort_checker.py examples/edge.toml
OK — 1 file(s) checked, every table key is sorted.
```

Keys inside a one-line inline table are checked
inside that table:

```sh
$ printf '[t]\npoint = {y = 2, x = 1}\n' | python3 src/toml_key_sort_checker.py --stdin
FAIL <stdin>: line 2 key "x" is out of order inside an inline table — it sorts before "y"
Checked 1 file(s), 1 key(s) out of order in 1 file(s).
```

A file that is not valid TOML is reported instead
of being order-checked:

```sh
$ printf 'key = [\n' | python3 src/toml_key_sort_checker.py --stdin
FAIL <stdin>: not valid TOML: Invalid value (at end of document)
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_toml_key_sort_checker.py
```

The tests cover key order (sorted keys pass, an
out-of-order key fails with key and previous, several
bad keys in document order, case-insensitive order,
equal keys do not fail, numbers sort as characters,
a table header starts a new order, an out-of-order
key inside a table, an array-of-tables header starts
a new order, comments and blank lines ignored, a
comment with an equals sign is not a key, a `#`
inside a string is not a comment, quoted keys
compared unquoted, dotted keys compared in full,
dotted keys with spaces around the dots, a sorted
inline table passes, an out-of-order inline table
fails, a nested inline table has its own order, a
string with an equals sign inside an inline table
is ignored, multi-line string lines are not
checked, multi-line array lines are not checked, a
key after a multi-line array is checked, an empty
document passes, a document with only comments
passes, a line with no value is not a key), TOML
validation (an unparsable file reported, a
duplicate key reported, a valid file checked for
order), the CLI (exit 0/1/2, folder walking for
`.toml` files only, nested folders,
`--no-recursive`, `--exclude`, `.git` skipped, a
direct file checked whatever its name, duplicate
paths checked once, `--json` output, `--stdin`,
invalid TOML on stdin, bad flags, missing paths,
empty folders, `--version`, a non-UTF-8 file
reported, input files left unchanged, the tool
run from another folder and under a changed HOME),
the bundled examples (sample output compared
byte-for-byte against a fresh run, and the
README-quoted outputs checked against it), and
hygiene checks (no placeholder text, no absolute
paths, no real secrets outside the tests and
examples, stdlib imports only, no network use in
the source, `.env` first in `.gitignore`, CI file
runs the test file, README names the neighbouring
repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of sorting config keys is not new, and the
parsing follows Python's own standard-library TOML
parser — but no existing tool does this one job,
checking that every key in local TOML files is
sorted alphabetically, as a tested command-line
gate with a CI exit code, as the search above
shows — and every line of code here is original,
built on nothing but Python's standard library.

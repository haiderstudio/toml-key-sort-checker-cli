== examples/good.toml ==
OK — 1 file(s) checked, every table key is sorted.

== examples/bad.toml ==
FAIL examples/bad.toml: line 4 key "apple" is out of order — it sorts before "zebra"
FAIL examples/bad.toml: line 8 key "host" is out of order — it sorts before "port"
Checked 1 file(s), 2 key(s) out of order in 1 file(s).

== examples/edge.toml ==
OK — 1 file(s) checked, every table key is sorted.

== examples/ : the whole folder ==
FAIL examples/bad.toml: line 4 key "apple" is out of order — it sorts before "zebra"
FAIL examples/bad.toml: line 8 key "host" is out of order — it sorts before "port"
Checked 3 file(s), 2 key(s) out of order in 1 file(s).

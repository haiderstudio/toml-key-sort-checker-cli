# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the TOML files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL and never runs code from a TOML file — it only reads the text.

It only checks that table keys are sorted. It never executes a value, never loads a module, and never runs a command.

If you find a case where the tool rewrites a file, runs a command, or reports a pass for a TOML file with an out-of-order key, please open an issue describing the exact commands and input. Do not include any real secret in the report.

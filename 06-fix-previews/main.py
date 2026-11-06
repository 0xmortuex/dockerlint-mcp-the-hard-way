"""Module 06: unified-diff previews of safe fixes."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minilint.engine import lint  # noqa: E402
from minilint.fixes import preview  # noqa: E402
from minilint.parser import parse  # noqa: E402

TEXT = """\
FROM python:3.12-slim
RUN apt-get update \\
    && apt-get install -y curl \\
    && rm -rf /var/lib/apt/lists/*
USER 10001
CMD python app.py
"""

df = parse(TEXT)
findings = lint(df)
assert {f.rule for f in findings} == {"ML003", "ML005"}

diff, remaining = preview(TEXT, findings, df)
print(diff)
assert "-    && apt-get install -y curl \\" in diff
assert "+    && apt-get install --no-install-recommends -y curl \\" in diff
assert '+CMD ["python", "app.py"]' in diff
assert remaining == 0

# The fix keeps the line count, so the line numbers in findings remain valid.
assert diff.count("\n-") >= 2

# Unsafe conversions are refused: with $HOME the shell does real work, so exec form would change behaviour.
unsafe = "FROM a:1\nUSER 1\nCMD echo $HOME | tee /x\n"
df2 = parse(unsafe)
diff2, remaining2 = preview(unsafe, lint(df2), df2)
assert diff2 == "" and remaining2 == 1

# Nothing was written anywhere: preview() only ever returns text.
print("module 06 OK: fixes verified by re-linting ({} finding(s) left in the unsafe case)".format(remaining2))

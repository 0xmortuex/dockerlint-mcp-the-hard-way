"""Module 01: parse a deliberately nasty Dockerfile and check every structural claim."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minilint.parser import expand, parse  # noqa: E402

TEXT = """\
# syntax=docker/dockerfile:1
# escape=\\
ARG PY=3.12
FROM --platform=$BUILDPLATFORM python:${PY}-slim AS build
ENV A=1
RUN apt-get update \\
    # a comment INSIDE a continued instruction is dropped by Docker
    && apt-get install -y curl

RUN <<EOF
set -e
echo "# this is script text, not a Dockerfile comment"
EOF
COPY --from=build --chown=1000:1000 /a /b
CMD ["python", "app.py"]
FROM alpine:3.20
ONBUILD ADD . /app
CMD python app.py
"""

df = parse(TEXT)

# 1. Parser directives are only recognised at the top of the file.
assert df.directives == {"syntax": "docker/dockerfile:1", "escape": "\\"}

# 2. The continued RUN spans lines 6-8; the comment line is skipped, and the join is clean.
run = df.instructions[3]
assert (run.cmd, run.line, run.end_line) == ("RUN", 6, 8), (run.cmd, run.line, run.end_line)
assert "apt-get install -y curl" in run.args and "comment" not in run.args

# 3. A heredoc body is taken verbatim, so its '#' line is NOT treated as a comment.
heredoc_run = df.instructions[4]
assert heredoc_run.heredocs and "# this is script text" in heredoc_run.heredocs[0]
assert (heredoc_run.line, heredoc_run.end_line) == (10, 13)

# 4. Flags are split from arguments; JSON form is detected.
copy = df.instructions[5]
assert copy.flags == {"from": "build", "chown": "1000:1000"} and copy.args == "/a /b"
cmd_json, cmd_shell = df.instructions[6], df.instructions[-1]
assert cmd_json.json_form and cmd_json.argv == ["python", "app.py"]
assert not cmd_shell.json_form and cmd_shell.args == "python app.py"

# 5. Multi-stage structure, with ARG expansion applied to the FROM image.
assert [(s.index, s.name, s.image) for s in df.stages] == [(0, "build", "python:3.12-slim"), (1, None, "alpine:3.20")]
assert df.stages[0].instructions[0].cmd == "ENV"

# 6. ONBUILD instructions are kept but marked, because they do not run in THIS build.
onbuild = [i for i in df.instructions if i.onbuild]
assert len(onbuild) == 1 and onbuild[0].cmd == "ADD"

# 7. Variable expansion, on its own.
assert expand("${V:-1.0}-$W", {"W": "x"}) == ("1.0-x", True)
assert expand("$MISSING", {}) == ("$MISSING", False)

# 8. Garbage does not crash the parser; it is reported.
bad = parse("RUN echo hi\nFROM alpine:3.20\nINSTALL curl\nRUN <<X\nnever closed\n")
assert [m for _, m in sorted(bad.errors)] == [
    "RUN before the first FROM", "unknown instruction 'INSTALL'", "heredoc <<X is never closed",
]
assert parse("").instructions == [] and parse("\x00\x01").stages == []

print("module 01 OK: parsed", len(df.instructions), "instructions in", len(df.stages), "stages")

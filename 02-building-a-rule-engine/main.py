"""Module 02: run the rule engine on bad and good Dockerfiles."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minilint.engine import RULES, commands, lint  # noqa: E402
from minilint.parser import parse  # noqa: E402

BAD = """\
FROM python
RUN apt-get update
RUN echo "apt-get update is only a string here" && apt-get install -y curl
ENV DB_PASSWORD=hunter2
CMD python app.py
"""


def found(text, disabled=frozenset()):
    return [(f.rule, f.line) for f in lint(parse(text), disabled)]


got = found(BAD)
assert ("ML001", 1) in got  # unpinned base image
assert ("ML002", 2) in got  # apt-get update in its own layer
assert ("ML003", 3) in got  # missing --no-install-recommends (the echo text is NOT mistaken for a command)
assert ("ML002", 3) not in got
assert ("ML004", 1) in got  # runs as root
assert ("ML005", 5) in got  # shell-form CMD
assert ("ML006", 4) in got  # secret in ENV

# Secrets are reported by NAME, never by value.
for f in lint(parse(BAD)):
    assert "hunter2" not in f.message + f.fix
    assert f.fix  # every finding comes with a concrete fix

# commands() understands quoting and operators.
ins = parse("FROM a:1\nRUN a && b 'c && d' | e ; f\n").instructions[1]
assert commands(ins) == [["a"], ["b", "c && d"], ["e"], ["f"]]

# Suppression: a comment above the instruction silences that rule for that instruction only.
suppressed = "# minilint-ignore: ML001, ML004\nFROM python\nRUN apt-get update\nCMD [\"x\"]\n"
got = found(suppressed)
assert ("ML001", 2) not in got and ("ML004", 2) not in got and ("ML002", 3) in got

# Disabling: the --disable flag.
assert not [r for r, _ in found(BAD, frozenset({"ML001", "ML004"})) if r in ("ML001", "ML004")]

# False-positive guard: a well-written file produces nothing.
GOOD = """\
FROM python:3.12-slim
RUN apt-get update \\
    && apt-get install -y --no-install-recommends curl \\
    && rm -rf /var/lib/apt/lists/*
USER 10001
CMD ["python", "app.py"]
"""
assert found(GOOD) == [], found(GOOD)

print("module 02 OK:", len(RULES), "rules,", len(BAD.splitlines()), "line bad file ->", len(found(BAD)), "findings")

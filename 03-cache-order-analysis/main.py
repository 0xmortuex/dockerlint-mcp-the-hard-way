"""Module 03: layers and cache order."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minilint import layers  # noqa: E402
from minilint.engine import lint  # noqa: E402
from minilint.parser import parse  # noqa: E402

SLOW = """\
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN rm -rf /var/lib/apt/lists/*
USER 10001
CMD ["python", "app.py"]
"""

FAST = """\
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 10001
CMD ["python", "app.py"]
"""

got = {(f.rule, f.line) for f in lint(parse(SLOW))}
assert ("ML007", 3) in got, got  # COPY . . on line 3 comes before the install on line 4
assert ("ML008", 6) in got, got  # rm in its own layer cannot shrink line 5

fast = {f.rule for f in lint(parse(FAST))}
assert "ML007" not in fast and "ML008" not in fast

info = layers.explain(parse(SLOW))
by_line = {i.line: i for i in info}
assert by_line[2].makes_layer is False  # WORKDIR: metadata only
assert by_line[3].makes_layer and by_line[3].size_hint == "the whole build context"
assert by_line[4].size_hint == "large (dependencies)"
assert by_line[5].size_hint == "large (OS packages)"

# Installing BEFORE the big COPY is the good order, even with later installs of other things.
assert not [f for f in lint(parse(FAST)) if f.rule == "ML007"]

# `COPY --from` copies artifacts, not the build context.
multi = parse("FROM golang:1.23 AS b\nRUN true\nFROM alpine:3.20\nCOPY --from=b /app /app\nRUN pip install -r r.txt\n")
assert not [f for f in lint(multi) if f.rule == "ML007"]

print("module 03 OK: cache-order rules flag the slow file and accept the fast one")

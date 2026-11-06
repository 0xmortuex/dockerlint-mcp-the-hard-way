"""Module 04: compose analysis with line numbers."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import yaml  # noqa: E402

from minilint.compose import Locator, lint_compose  # noqa: E402

BAD = """\
services:
  web:
    image: nginx
    privileged: true
    ports:
      - "8080:80"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
  db:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: hunter2
      TZ: UTC
    ports:
      - "127.0.0.1:5432:5432"
"""

got = {(f.rule, f.line) for f in lint_compose(BAD)}
assert ("MC001", 3) in got  # nginx has no tag
assert ("MC002", 4) in got
assert ("MC005", 6) in got  # "8080:80" is on all interfaces; the 127.0.0.1 binding is fine
assert ("MC003", 8) in got
assert ("MC004", 12) in got
assert not [g for g in got if g[1] == 15], got

# Secret values are never echoed.
assert all("hunter2" not in f.message + f.fix for f in lint_compose(BAD))

# Line numbers come from scanning the text, because safe_load throws them away.
loc = Locator(BAD)
assert loc.blocks == {"web": (1, 7), "db": (8, 14)}
assert loc.find("db", r"POSTGRES_PASSWORD") == 12

# safe_load refuses to construct arbitrary Python objects (this is why we never use yaml.load).
try:
    lint_compose("services:\n  a: !!python/object/apply:os.system ['echo pwned']\n")
except yaml.YAMLError:
    pass
else:
    raise AssertionError("safe_load should have rejected the python tag")

# Not a compose file at all.
try:
    lint_compose("hello: world\n")
except ValueError as e:
    assert "services" in str(e)
else:
    raise AssertionError("expected ValueError")

GOOD = """\
services:
  web:
    image: ghcr.io/acme/web:1.4.2
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      DATABASE_URL: ${DATABASE_URL}
"""
assert lint_compose(GOOD) == []

print("module 04 OK:", len(got), "compose findings located by line")

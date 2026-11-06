"""Module 05: .dockerignore matching.

NOT the same as .gitignore. The rules (from Docker's own matcher):
  * patterns are anchored at the context root: `node_modules` does not match `a/node_modules`
  * `*` and `?` never cross a `/`; `**` does
  * a pattern that matches a directory excludes everything under it
  * the LAST matching pattern wins; a leading `!` re-includes
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    out = ["^"]
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 2] == "**":
                while i + 1 < len(pattern) and pattern[i + 1] == "*":
                    i += 1
                if pattern[i + 1 : i + 2] == "/":
                    i += 1
                    out.append("(?:.*/)?")  # `**/` = zero or more directories
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(c))
        i += 1
    out.append("$")
    return re.compile("".join(out))


@dataclass
class Pattern:
    raw: str
    line: int
    negate: bool
    regex: re.Pattern[str]


class IgnoreMatcher:
    def __init__(self, text: str) -> None:
        self.patterns: list[Pattern] = []
        for no, raw in enumerate(text.splitlines(), start=1):
            p = raw.strip()
            if not p or p.startswith("#"):
                continue
            negate = p.startswith("!")
            if negate:
                p = p[1:].strip()
            p = posixpath.normpath(p).lstrip("/")  # `./x`, `x/` and `/x` all mean `x`
            self.patterns.append(Pattern(raw.strip(), no, negate, glob_to_regex(p)))

    def match(self, path: str) -> tuple[bool, Pattern | None]:
        parts = posixpath.normpath(path).split("/")
        # Test the path itself and each parent directory: excluding `docs` excludes `docs/a.md`.
        candidates = ["/".join(parts[: k + 1]) for k in range(len(parts))]
        excluded, decider = False, None
        for pat in self.patterns:  # in order: the last match wins
            if any(pat.regex.match(c) for c in candidates):
                excluded, decider = not pat.negate, pat
        return excluded, decider

    def excludes(self, path: str) -> bool:
        return self.match(path)[0]

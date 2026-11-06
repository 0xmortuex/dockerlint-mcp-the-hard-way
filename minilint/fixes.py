"""Module 06: fix previews.

A fix preview rewrites the *physical lines* of an instruction in memory, never changes
the number of lines (so reported line numbers stay valid), re-lints the result to prove it
helped, and shows a unified diff. It never writes the file.
"""

from __future__ import annotations

import difflib
import json
import re
import shlex
from collections.abc import Callable

from .engine import Finding, lint
from .parser import Dockerfile, Instruction, parse

SAFE_WORD = re.compile(r"^[\w./:=@%+,-]+$")


def fix_recommends(lines: list[str], ins: Instruction) -> bool:
    """apt-get install x  ->  apt-get install --no-install-recommends x"""
    changed = False
    for k in range(ins.line - 1, ins.end_line):
        if "--no-install-recommends" in lines[k]:
            continue
        new = re.sub(r"\bapt-get install\b", "apt-get install --no-install-recommends", lines[k])
        if new != lines[k]:
            lines[k], changed = new, True
    return changed


def fix_shell_form(lines: list[str], ins: Instruction) -> bool:
    """CMD python app.py  ->  CMD ["python", "app.py"], only when no shell feature is involved."""
    if ins.line != ins.end_line:
        return False
    try:
        words = shlex.split(ins.args)
    except ValueError:
        return False
    if not words or not all(SAFE_WORD.match(w) for w in words):
        return False  # $VAR, pipes, quotes...: the shell is doing real work; leave it to a human
    lines[ins.line - 1] = f"{ins.cmd} {json.dumps(words)}"
    return True


FIXERS: dict[str, Callable[[list[str], Instruction], bool]] = {
    "ML003": fix_recommends,
    "ML005": fix_shell_form,
}


def preview(text: str, findings: list[Finding], df: Dockerfile) -> tuple[str, int]:
    """Return (unified diff, number of findings that remain after the fixes)."""
    original = text.splitlines()
    fixed = list(original)
    done: set[tuple[str, int]] = set()
    for f in findings:
        ins = df.instruction_at(f.line)
        fixer = FIXERS.get(f.rule)
        if ins is not None and fixer is not None and (f.rule, ins.line) not in done:
            if fixer(fixed, ins):
                done.add((f.rule, ins.line))
    assert len(fixed) == len(original), "a fix must not add or remove lines"
    remaining = len(lint(parse("\n".join(fixed) + "\n")))
    diff = "\n".join(difflib.unified_diff(original, fixed, "a/Dockerfile", "b/Dockerfile", lineterm=""))
    return diff, remaining

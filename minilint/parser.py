"""Module 01: a Dockerfile parser.

Turns text into instructions. It handles the parts of the grammar that trip up
regex-based linters: line continuations (with comments inside them), parser
directives, heredocs, JSON vs shell form, flags, and multi-stage structure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

KNOWN = {
    "FROM", "RUN", "CMD", "LABEL", "MAINTAINER", "EXPOSE", "ENV", "ADD", "COPY", "ENTRYPOINT",
    "VOLUME", "USER", "WORKDIR", "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL",
}
DIRECTIVE = re.compile(r"^\s*#\s*(syntax|escape|check)\s*=\s*(.*?)\s*$", re.I)
IGNORE = re.compile(r"^\s*#\s*minilint-ignore\s*:\s*(.+?)\s*$", re.I)
RULE_ID = re.compile(r"[A-Za-z]{2}\d{3}")
HEREDOC = re.compile(r"(?<!<)<<(-?)([\"']?)([A-Za-z_]\w*)\2(?!<)")
FLAG = re.compile(r"--([A-Za-z][\w-]*)(?:=(\S*))?(?=\s|$)")


@dataclass
class Instruction:
    cmd: str  # upper-case keyword (for ONBUILD: the inner keyword)
    args: str  # text after the flags, continuations joined
    line: int  # first physical line, 1-based
    end_line: int  # last physical line, including heredoc bodies
    flags: dict[str, str] = field(default_factory=dict)
    json_form: bool = False
    argv: list[str] = field(default_factory=list)
    heredocs: list[str] = field(default_factory=list)  # bodies
    ignores: set[str] = field(default_factory=set)
    onbuild: bool = False
    stage: int = -1


@dataclass
class Stage:
    index: int
    name: str | None
    image: str
    line: int
    instructions: list[Instruction] = field(default_factory=list)  # excluding FROM


@dataclass
class Dockerfile:
    lines: list[str]
    instructions: list[Instruction]
    stages: list[Stage]
    directives: dict[str, str]
    errors: list[tuple[int, str]]

    def instruction_at(self, line: int) -> Instruction | None:
        for ins in self.instructions:
            if ins.line <= line <= ins.end_line:
                return ins
        return None


def ignore_ids(comment: str) -> set[str]:
    m = IGNORE.match(comment)
    return {i.upper() for i in RULE_ID.findall(m.group(1))} if m else set()


def parse(text: str) -> Dockerfile:
    lines = re.split(r"\r\n|\r|\n", text)
    n = len(lines)

    # Parser directives are only valid at the very top.
    directives: dict[str, str] = {}
    i = 0
    while i < n and (m := DIRECTIVE.match(lines[i])):
        directives[m.group(1).lower()] = m.group(2)
        i += 1
    escape = directives.get("escape", "\\")
    continuation = re.compile(re.escape(escape) + r"[ \t]*$")

    instructions: list[Instruction] = []
    errors: list[tuple[int, str]] = []
    pending: set[str] = set()  # ignore ids from comments above the next instruction
    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            pending |= ignore_ids(stripped)
            i += 1
            continue

        start, ignores, pending = i, set(pending), set()
        parts: list[str] = []
        piece = raw
        while (m := continuation.search(piece)):
            parts.append(piece[: m.start()])
            i += 1
            # Comments and blank lines may sit INSIDE a continued instruction; Docker drops them.
            while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
                ignores |= ignore_ids(lines[i].strip())
                i += 1
            if i >= n:
                piece = ""
                break
            piece = lines[i]
        parts.append(piece)
        end = min(i, n - 1)
        i += 1

        km = re.match(r"\s*(\S+)\s*(.*)$", "".join(parts), re.S)
        if not km:
            continue
        keyword, rest = km.group(1), km.group(2).strip()
        onbuild = keyword.upper() == "ONBUILD"
        if onbuild:
            km = re.match(r"(\S+)\s*(.*)$", rest, re.S)
            if not km:
                errors.append((start + 1, "ONBUILD needs an instruction"))
                continue
            keyword, rest = km.group(1), km.group(2).strip()
        cmd = keyword.upper()
        if cmd not in KNOWN:
            errors.append((start + 1, f"unknown instruction '{keyword}'"))
            continue

        flags: dict[str, str] = {}
        if cmd in ("FROM", "RUN", "COPY", "ADD", "HEALTHCHECK"):
            while rest.startswith("--") and (fm := FLAG.match(rest)):
                flags[fm.group(1)] = fm.group(2) or ""
                rest = rest[fm.end():].lstrip()
        ins = Instruction(cmd, rest, start + 1, end + 1, flags, ignores=ignores, onbuild=onbuild)
        if cmd in ("RUN", "CMD", "ENTRYPOINT", "COPY", "ADD", "VOLUME", "SHELL"):
            try:
                val = json.loads(rest) if rest.startswith("[") else None
            except (ValueError, RecursionError):
                val = None
            if isinstance(val, list) and all(isinstance(x, str) for x in val):
                ins.json_form, ins.argv = True, list(val)

        # Heredoc bodies follow the instruction line verbatim, up to the delimiter.
        if cmd in ("RUN", "COPY", "ADD") and not ins.json_form:
            for hm in HEREDOC.finditer(rest):
                dash, delim = hm.group(1), hm.group(3)
                body: list[str] = []
                closed = False
                while i < n:
                    ln = lines[i]
                    i += 1
                    if (ln.lstrip("\t") if dash else ln) == delim:
                        closed = True
                        break
                    body.append(ln)
                if not closed:
                    errors.append((start + 1, f"heredoc <<{delim} is never closed"))
                ins.heredocs.append("\n".join(body))
                ins.end_line = max(ins.end_line, i)
        instructions.append(ins)

    return Dockerfile(lines, instructions, build_stages(instructions, errors), directives, errors)


def expand(s: str, env: dict[str, str]) -> tuple[str, bool]:
    """Expand $VAR, ${VAR} and ${VAR:-default}. Returns (text, fully_resolved)."""
    ok = True

    def sub(m: re.Match[str]) -> str:
        nonlocal ok
        name = m.group(1) or m.group(3)
        if name in env:
            return env[name]
        if m.group(2) is not None:
            return m.group(2)
        ok = False
        return m.group(0)

    return re.sub(r"\$\{([A-Za-z_]\w*)(?::-([^}]*))?\}|\$([A-Za-z_]\w*)", sub, s), ok


def build_stages(instructions: list[Instruction], errors: list[tuple[int, str]]) -> list[Stage]:
    stages: list[Stage] = []
    global_args: dict[str, str] = {}
    for ins in instructions:
        if ins.cmd == "FROM":
            m = re.match(r"(\S+)(?:\s+(?i:as)\s+(\S+))?\s*$", ins.args)
            if not m:
                errors.append((ins.line, "FROM needs an image"))
                continue
            image, _ = expand(m.group(1), global_args)  # only ARGs before the first FROM count here
            stages.append(Stage(len(stages), m.group(2).lower() if m.group(2) else None, image, ins.line))
            ins.stage = stages[-1].index
        elif not stages:
            if ins.cmd == "ARG":
                k, eq, v = ins.args.partition("=")
                if eq:
                    global_args[k.strip()] = v.strip()
            else:
                errors.append((ins.line, f"{ins.cmd} before the first FROM"))
        else:
            ins.stage = stages[-1].index
            stages[-1].instructions.append(ins)
    return stages

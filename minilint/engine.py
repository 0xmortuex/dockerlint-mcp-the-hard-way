"""Module 02: a rule engine.

A rule is a function that looks at a parsed Dockerfile and yields hits. The engine
runs every enabled rule, applies `# minilint-ignore:` comments, and sorts the result.
Rules never look at raw text: they look at parsed *commands*, so `echo "apt-get update"`
is not mistaken for a real apt-get call.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .parser import Dockerfile, Instruction

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    rule: str
    severity: str
    line: int
    message: str
    fix: str


@dataclass
class Hit:
    line: int
    message: str
    fix: str


RULES: dict[str, str] = {}  # id -> severity
_CHECKS: list[tuple[str, Callable[[Dockerfile], Iterable[Hit]]]] = []


def rule(rule_id: str, severity: str):
    def deco(fn):
        RULES[rule_id] = severity
        _CHECKS.append((rule_id, fn))
        return fn

    return deco


def lint(df: Dockerfile, disabled: frozenset[str] = frozenset()) -> list[Finding]:
    out: list[Finding] = []
    for rid, check in _CHECKS:
        if rid in disabled:  # the --disable flag
            continue
        for hit in check(df):
            ins = df.instruction_at(hit.line)
            if ins is not None and rid in ins.ignores:  # the # minilint-ignore: comment
                continue
            out.append(Finding(rid, RULES[rid], hit.line, hit.message, hit.fix))
    out.sort(key=lambda f: (f.line, SEVERITY_ORDER[f.severity], f.rule))
    return out


# ------------------------------------------------------------------ shell commands

_SEPARATORS = {"&&", "||", ";", "|", "&"}


def commands(ins: Instruction) -> list[list[str]]:
    """Split a RUN into commands: `a && b | c` -> [[a], [b], [c]]."""
    if ins.json_form:
        return [list(ins.argv)]
    text = ins.args + "\n" + "\n".join(ins.heredocs)
    text = re.sub(r"\\\n", " ", text).replace("\n", " ; ")
    lex = shlex.shlex(text, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    out: list[list[str]] = []
    cur: list[str] = []
    try:
        for tok in lex:
            if tok in _SEPARATORS:
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(tok)
    except ValueError:
        pass  # unbalanced quote: Docker would reject it too
    if cur:
        out.append(cur)
    return out


def runs(df: Dockerfile) -> Iterable[Instruction]:
    return (i for i in df.instructions if i.cmd == "RUN" and not i.onbuild)


# ------------------------------------------------------------------ rules


@rule("ML001", "warning")
def latest_tag(df: Dockerfile) -> Iterable[Hit]:
    for st in df.stages:
        name, _, tag = st.image.partition(":")
        if st.image == "scratch" or "@" in st.image or "$" in st.image:
            continue
        if not tag or tag == "latest":
            yield Hit(st.line, f"{st.image} is not pinned to a version.", f"Use e.g. `FROM {name}:<version>`.")


@rule("ML002", "warning")
def apt_update_alone(df: Dockerfile) -> Iterable[Hit]:
    for ins in runs(df):
        cmds = commands(ins)
        update = any(c[:2] == ["apt-get", "update"] for c in cmds)
        install = any(c[:2] == ["apt-get", "install"] for c in cmds)
        if update and not install:
            yield Hit(
                ins.line,
                "apt-get update in its own layer gets cached and goes stale.",
                "`RUN apt-get update && apt-get install -y --no-install-recommends <pkgs>`",
            )


@rule("ML003", "warning")
def recommends(df: Dockerfile) -> Iterable[Hit]:
    for ins in runs(df):
        for c in commands(ins):
            if c[:2] == ["apt-get", "install"] and "--no-install-recommends" not in c:
                yield Hit(ins.line, "Recommended packages bloat the image.", "Add --no-install-recommends.")
                break


@rule("ML004", "warning")
def root_user(df: Dockerfile) -> Iterable[Hit]:
    if not df.stages:
        return
    last = df.stages[-1]
    users = [i for i in last.instructions if i.cmd == "USER"]
    if not users or users[-1].args.split(":")[0] in ("root", "0"):
        yield Hit(last.line, "The container runs as root.", "Add `USER <non-root user>` before CMD.")


@rule("ML005", "warning")
def shell_form(df: Dockerfile) -> Iterable[Hit]:
    for ins in df.instructions:
        if ins.cmd in ("CMD", "ENTRYPOINT") and not ins.onbuild and not ins.json_form:
            yield Hit(
                ins.line,
                f"Shell-form {ins.cmd}: the shell is PID 1 and swallows SIGTERM.",
                f'Use exec form: {ins.cmd} ["program", "arg"]',
            )


_SECRET = re.compile(r"(PASS(WORD)?|SECRET|TOKEN|API_?KEY)", re.I)


@rule("ML006", "error")
def secret_in_env(df: Dockerfile) -> Iterable[Hit]:
    for ins in df.instructions:
        if ins.cmd not in ("ENV", "ARG"):
            continue
        for word in shlex.split(ins.args):
            name, eq, value = word.partition("=")
            if eq and value and not value.startswith("$") and _SECRET.search(name):
                # Report the NAME only. A linter that echoes secrets is itself a leak.
                yield Hit(ins.line, f"{name} is a hard-coded secret (value hidden).", "Pass it at runtime or use a build secret.")

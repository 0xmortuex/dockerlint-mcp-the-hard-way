"""Module 03: layers and cache-order analysis.

Docker caches each layer by (parent layer, instruction text, and for COPY/ADD the
content of the copied files). The moment one layer changes, every layer after it is
rebuilt. So order matters: things that change rarely go first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engine import Hit, commands, rule, runs
from .parser import Dockerfile, Instruction

LAYER_CMDS = {"RUN", "COPY", "ADD"}  # everything else only changes image metadata


def is_dependency_install(cmd: list[str]) -> bool:
    """Does this command install the project's dependencies?"""
    if not cmd:
        return False
    name, args = cmd[0], cmd[1:]
    if name in ("pip", "pip3") and "install" in args:
        return "-r" in args or "--requirement" in args
    if name in ("npm", "pnpm", "yarn") and args[:1] in (["ci"], ["install"], ["i"]):
        return "-g" not in args
    if name == "go" and args[:2] == ["mod", "download"]:
        return True
    if name == "bundle" and "install" in args:
        return True
    return False


def installs_dependencies(ins: Instruction) -> bool:
    return ins.cmd == "RUN" and any(is_dependency_install(c) for c in commands(ins))


def copies_everything(ins: Instruction) -> bool:
    """`COPY . .` and friends: the layer changes whenever ANY source file changes."""
    if ins.cmd not in ("COPY", "ADD") or "from" in ins.flags:
        return False
    words = ins.args.split()
    return any(w in (".", "./", "*") for w in words[:-1])


@dataclass
class LayerInfo:
    line: int
    cmd: str
    makes_layer: bool
    size_hint: str


def size_hint(ins: Instruction) -> str:
    if ins.cmd in ("COPY", "ADD"):
        if "from" in ins.flags:
            return "only the copied artifacts"
        return "the whole build context" if copies_everything(ins) else "the copied files"
    if ins.cmd != "RUN":
        return "metadata only"
    cmds = commands(ins)
    if any(c[:2] in (["apt-get", "install"], ["apk", "add"]) for c in cmds):
        return "large (OS packages)"
    if any(is_dependency_install(c) for c in cmds):
        return "large (dependencies)"
    return "small or unknown"


def explain(df: Dockerfile) -> list[LayerInfo]:
    return [
        LayerInfo(i.line, i.cmd, i.cmd in LAYER_CMDS, size_hint(i))
        for st in df.stages
        for i in st.instructions
    ]


@rule("ML007", "warning")
def copy_before_install(df: Dockerfile) -> list[Hit]:
    """COPY . before the dependency install: every source edit re-installs everything."""
    hits: list[Hit] = []
    for st in df.stages:
        copy_all: Instruction | None = None
        for ins in st.instructions:
            if copies_everything(ins) and copy_all is None:
                copy_all = ins
            elif copy_all is not None and installs_dependencies(ins):
                hits.append(Hit(
                    copy_all.line,
                    f"Everything is copied before dependencies are installed (line {ins.line}).",
                    "Copy only requirements.txt / package*.json / go.mod first, install, THEN `COPY . .`.",
                ))
                break
            elif copy_all is None and installs_dependencies(ins):
                break  # installed before the big COPY: the good order
    return hits


@rule("ML008", "warning")
def cleanup_in_later_layer(df: Dockerfile) -> list[Hit]:
    """`RUN rm -rf ...` in its own layer cannot shrink the earlier layer that created the files."""
    hits: list[Hit] = []
    for st in df.stages:
        prev: Instruction | None = None
        for ins in st.instructions:
            if ins.cmd == "RUN" and prev is not None and prev.cmd == "RUN":
                cmds = commands(ins)
                if cmds and all(c[0] == "rm" for c in cmds):
                    hits.append(Hit(
                        ins.line,
                        f"Files removed here still exist in the layer on line {prev.line}.",
                        "Delete in the same RUN that created them: `RUN <install> && rm -rf <cache>`.",
                    ))
            if ins.cmd in LAYER_CMDS:
                prev = ins
    return hits


__all__ = ["explain", "runs"]

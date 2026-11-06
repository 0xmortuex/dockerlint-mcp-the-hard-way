"""Module 07: the MCP wrapper.

Three tools over a sandboxed directory. mcp>=2 only forwards a ToolError's message to the
client; any other exception becomes a bare "Error executing tool". So expected failures are
converted to ToolError at the boundary.
"""

from __future__ import annotations

import argparse
import functools
import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import layers  # noqa: F401  (importing registers the cache-order rules)
from .compose import lint_compose as lint_compose_text
from .engine import Finding, lint
from .fixes import preview
from .parser import parse

mcp = MCPServer("minilint", instructions="Lint Dockerfiles and compose files without Docker.")
ROOT = os.getcwd()
MAX_BYTES = 1_000_000


def resolve(path: str) -> str:
    """Resolve `path` inside ROOT. Symlinks are resolved first so they cannot escape."""
    real = os.path.realpath(os.path.join(ROOT, path))
    root = os.path.realpath(ROOT)
    if os.path.commonpath([os.path.normcase(real), os.path.normcase(root)]) != os.path.normcase(root):
        raise ToolError(f"{path!r} is outside the allowed directory ({root}).")
    if not os.path.isfile(real):
        raise ToolError(f"File not found: {path!r} (relative paths are resolved against {root}).")
    if os.path.getsize(real) > MAX_BYTES:
        raise ToolError(f"{path!r} is larger than {MAX_BYTES} bytes.")
    return real


def read(path: str) -> str:
    with open(resolve(path), "rb") as fh:
        try:
            return fh.read().decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ToolError(f"{path!r} is not UTF-8 text.") from e


def render(findings: list[Finding]) -> str:
    if not findings:
        return "0 findings."
    lines = [f"{len(findings)} finding(s):"]
    for f in findings:
        lines.append(f"[{f.rule}] {f.severity} line {f.line}: {f.message}\n    fix: {f.fix}")
    return "\n".join(lines)


def tool(fn: Any) -> Any:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ValueError as e:  # includes YAML errors we re-raise as ValueError
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


@tool
def lint_dockerfile(path: str) -> str:
    """Lint a Dockerfile: rule id, severity, line number and a concrete fix per finding."""
    return render(lint(parse(read(path))))


@tool
def lint_compose(path: str) -> str:
    """Lint a docker-compose file: privileged, docker.sock, secrets, unpinned images, open ports."""
    import yaml

    try:
        return render(lint_compose_text(read(path)))
    except yaml.YAMLError as e:
        raise ToolError(f"{path!r} is not valid YAML: {e}") from e


@tool
def fix_preview(path: str) -> str:
    """Show a unified diff of the safe automatic fixes for a Dockerfile. Never writes the file."""
    text = read(path)
    df = parse(text)
    diff, remaining = preview(text, lint(df), df)
    return (diff or "No automatic fix applies.") + f"\n\n{remaining} finding(s) remain after these fixes."


def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.getcwd())
    ROOT = os.path.realpath(ap.parse_args().dir)
    mcp.run()


if __name__ == "__main__":
    main()

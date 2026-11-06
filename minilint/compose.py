"""Module 04: compose analysis.

`yaml.safe_load` gives us data but throws away line numbers, so findings are located
by scanning the text for the service block and the key inside it.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from .engine import Finding

COMPOSE_RULES = {
    "MC001": "warning",  # unpinned image
    "MC002": "error",    # privileged
    "MC003": "error",    # docker.sock
    "MC004": "error",    # secret in environment
    "MC005": "info",     # port bound to all interfaces
}
_SECRET = re.compile(r"(PASS(WORD)?|SECRET|TOKEN|API_?KEY)", re.I)


class Locator:
    """Find the 1-based line of a service or of a key inside it."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()
        self.blocks: dict[str, tuple[int, int]] = {}
        start = next((i for i, ln in enumerate(self.lines) if re.match(r"^services\s*:", ln)), None)
        if start is None:
            return
        indent: int | None = None
        name: str | None = None
        begin = 0
        for i in range(start + 1, len(self.lines)):
            ln = self.lines[i]
            if not ln.strip() or ln.lstrip().startswith("#"):
                continue
            ind = len(ln) - len(ln.lstrip())
            if ind == 0:
                break
            indent = ind if indent is None else indent
            m = re.match(r"^\s*([^\s:#]+)\s*:", ln)
            if ind == indent and m:
                if name is not None:
                    self.blocks[name] = (begin, i - 1)
                name, begin = m.group(1), i
        if name is not None:
            self.blocks[name] = (begin, len(self.lines) - 1)

    def find(self, service: str, pattern: str) -> int:
        a, b = self.blocks.get(service, (0, 0))
        for i in range(a, b + 1):
            if re.search(pattern, self.lines[i]):
                return i + 1
        return a + 1  # fall back to the service line


def lint_compose(text: str) -> list[Finding]:
    data: Any = yaml.safe_load(text)  # safe_load: never construct arbitrary Python objects
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ValueError("no top-level `services:` mapping; not a compose file")
    loc = Locator(text)
    out: list[Finding] = []

    def add(rule: str, line: int, message: str, fix: str) -> None:
        out.append(Finding(rule, COMPOSE_RULES[rule], line, message, fix))

    for name, svc in data["services"].items():
        if not isinstance(svc, dict):
            continue
        image = svc.get("image")
        if isinstance(image, str):
            tag = image.rpartition(":")[2] if ":" in image.rsplit("/", 1)[-1] else ""
            if "@" not in image and tag in ("", "latest"):
                add("MC001", loc.find(name, r"^\s*image\s*:"), f"{name}: image {image} is not pinned.",
                    "Pin a version tag or digest.")
        if svc.get("privileged") is True:
            add("MC002", loc.find(name, r"^\s*privileged\s*:"), f"{name} runs privileged.",
                "Remove it; add only the capabilities you need.")
        for v in svc.get("volumes") or []:
            if isinstance(v, str) and "docker.sock" in v:
                add("MC003", loc.find(name, r"docker\.sock"), f"{name} mounts the Docker socket (root on the host).",
                    "Remove it or use a restricted socket proxy.")
        env = svc.get("environment") or {}
        pairs = env.items() if isinstance(env, dict) else [e.partition("=")[::2] for e in env if isinstance(e, str)]
        for key, value in pairs:
            if _SECRET.search(str(key)) and value and not str(value).startswith("$"):
                add("MC004", loc.find(name, r"^\s*-?\s*" + re.escape(str(key)) + r"\s*[:=]"),
                    f"{name}: {key} is a hard-coded secret (value hidden).", "Use ${VAR} from a git-ignored .env file.")
        for p in svc.get("ports") or []:
            if isinstance(p, str) and p.count(":") == 1:  # "8080:80": no host IP means all interfaces
                add("MC005", loc.find(name, re.escape(p.split("/")[0])), f"{name} publishes {p} on all interfaces.",
                    f'Bind to loopback: "127.0.0.1:{p}"')
    out.sort(key=lambda f: (f.line, f.rule))
    return out

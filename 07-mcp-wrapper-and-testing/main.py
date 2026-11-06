"""Module 07: launch the real server over stdio, list its tools, call them, and attack it."""

import os
import sys
import tempfile

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

DOCKERFILE = "FROM python\nRUN apt-get update && apt-get install curl\nENV DB_PASSWORD=hunter2\nCMD python app.py\n"
COMPOSE = "services:\n  web:\n    image: nginx:latest\n    privileged: true\n"


async def run(workdir: str) -> None:
    outside = os.path.join(os.path.dirname(workdir), "outside.txt")
    with open(outside, "w", encoding="utf-8") as fh:
        fh.write("FROM alpine:3.20\n")
    for name, text in (("Dockerfile", DOCKERFILE), ("docker-compose.yml", COMPOSE), ("bad.yml", "services: [oops\n")):
        with open(os.path.join(workdir, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "minilint.server", "--dir", workdir],
        env={**os.environ, "PYTHONPATH": os.path.abspath(ROOT), "PYTHONIOENCODING": "utf-8"},
    )
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        names = {t.name for t in (await session.list_tools()).tools}
        assert names == {"lint_dockerfile", "lint_compose", "fix_preview"}, names

        res = await session.call_tool("lint_dockerfile", {"path": "Dockerfile"})
        text = res.content[0].text
        assert not res.is_error and "[ML001] warning line 1" in text and "[ML006] error line 3" in text
        assert "hunter2" not in text  # the secret never reaches the model

        res = await session.call_tool("lint_compose", {"path": "docker-compose.yml"})
        assert "[MC002] error line 4" in res.content[0].text

        res = await session.call_tool("fix_preview", {"path": "Dockerfile"})
        assert "--no-install-recommends" in res.content[0].text

        # Errors the agent can act on must survive the trip (mcp>=2 only forwards ToolError messages).
        res = await session.call_tool("lint_dockerfile", {"path": "missing"})
        assert res.is_error and "File not found" in res.content[0].text
        res = await session.call_tool("lint_dockerfile", {"path": "../outside.txt"})
        assert res.is_error and "outside the allowed directory" in res.content[0].text
        res = await session.call_tool("lint_compose", {"path": "bad.yml"})
        assert res.is_error and "not valid YAML" in res.content[0].text


def main() -> None:
    with tempfile.TemporaryDirectory() as parent:
        workdir = os.path.join(parent, "project")
        os.mkdir(workdir)
        anyio.run(run, workdir)
    print("module 07 OK: server lists 3 tools, answers over stdio, and refuses traversal")


main()

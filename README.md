# dockerlint-mcp, The Hard Way

Build an MCP server that lets an AI lint Dockerfiles and compose files **without Docker**. Start from
"what is a Dockerfile, grammatically?" and end with a tested stdio server. No hadolint, no daemon, no
framework doing the hard part for you.

At the end you will have built a small version of
[dockerlint-mcp](https://github.com/0xmortuex/dockerlint-mcp) yourself, and you will understand the three
things most lint tools get wrong: **parsing** (regexes over raw text lie), **rule design** (findings need
a line number and a concrete fix, and must never leak secrets), and **domain rules** that look like
something familiar but are not (`.dockerignore` is not `.gitignore`).

## Why This Exists

Most "linter" tutorials are a list of regexes. That breaks the first time someone writes

```dockerfile
RUN apt-get update \
    # pin the mirror
    && apt-get install -y curl
```

or `RUN echo "apt-get update"`, or a heredoc. A linter an AI relies on has to be right about structure
first, and quiet when the file is fine: every false positive teaches the model to ignore you.

## Who This Is For

- Developers who built a hello-world MCP server and want a real one
- Anyone who writes Dockerfiles and wants to know *why* the usual advice is the usual advice
- Anyone curious how a Dockerfile is actually tokenized

**Prerequisites:** Python and a rough idea of what `docker build` does. No Docker installation is needed;
nothing here ever runs a container.

```bash
pip install -r requirements.txt
python verify.py          # runs every module and checks it
```

## Modules

| # | Module | What You'll Build |
|---|--------|-------------------|
| 01 | [Dockerfile Grammar](01-dockerfile-grammar/) | A parser: continuations with comments inside, directives, heredocs, JSON vs shell form, flags, stages, ARG expansion |
| 02 | [Building a Rule Engine](02-building-a-rule-engine/) | `@rule`, findings with a fix, shell-command splitting, ignore comments, a disable flag, a false-positive guard |
| 03 | [Cache-Order Analysis](03-cache-order-analysis/) | Which instructions make layers, size hints, and why `COPY . .` before `pip install` is slow |
| 04 | [Compose Analysis](04-compose-analysis/) | `yaml.safe_load`, getting line numbers back, privileged / docker.sock / secrets / open ports |
| 05 | [Dockerignore Matching](05-dockerignore-matching/) | Docker's glob rules, root anchoring, `**`, negation, and checking the ignore file against your `COPY`s |
| 06 | [Fix Previews](06-fix-previews/) | Safe automatic fixes as a unified diff, verified by re-linting, never written |
| 07 | [MCP Wrapper and Testing](07-mcp-wrapper-and-testing/) | A sandboxed stdio server, `ToolError` at the boundary, and a test that launches it for real |

The code lives in [`minilint/`](minilint/), one file per module, and grows as you go. Each module has a
`main.py` that exercises that stage and checks its own claims with `assert`; `verify.py` runs them all.

## Design rules that run through every module

1. **Parse, then judge.** Rules look at parsed commands, never at raw text.
2. **Every finding has a line number and a concrete fix.** "Consider improving caching" is not a finding.
3. **Never echo a secret.** Report the variable name; the value stays out of the model's context.
4. **Stay quiet on good files.** A false-positive corpus is part of the test suite.
5. **Static means static.** Nothing is built, run, pulled or written.
6. **Fail loudly and usefully.** Errors say what to do next.

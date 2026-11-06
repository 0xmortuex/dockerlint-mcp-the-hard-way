# Module 07: MCP Wrapper and Testing

## The Concept

Everything so far is a library. An MCP server is a thin layer that exposes it to a model over stdio.
[`minilint/server.py`](../minilint/server.py) has three tools (`lint_dockerfile`, `lint_compose`,
`fix_preview`) and four jobs worth getting right.

### 1. Errors must be `ToolError`s

With `mcp>=2`, the client only receives the message of a `ToolError`. Any other exception turns into the
useless "Error executing tool lint_dockerfile". So expected failures are converted at the tool boundary
with a message that says what to do next:

```python
raise ToolError(f"File not found: {path!r} (relative paths are resolved against {root}).")
```

Genuine bugs are deliberately *not* converted, so they surface as bugs rather than being disguised as user
errors.

### 2. Sandbox every path

The model supplies the path, and the model is steered by whatever text it has read. Treat it as hostile:

```python
real = os.path.realpath(os.path.join(ROOT, path))      # resolves symlinks and ..
if os.path.commonpath([normcase(real), normcase(root)]) != normcase(root):
    raise ToolError("... outside the allowed directory ...")
```

`commonpath` rather than `startswith`: `/proj-evil` starts with `/proj` but is not inside it. `realpath`
before the check so a symlink inside the directory cannot point out of it. `normcase` for Windows.
Also cap the file size and refuse non-UTF-8 files with a clear message.

### 3. Tool design

Few tools with excellent descriptions beat many tools with vague ones. Each docstring says what the tool
does, what it returns and what it never does ("Never writes the file"), because that text is what the model
reads when deciding which tool to call.

### 4. Test it for real

Unit tests prove the library. They do not prove the server starts, lists its tools, or that errors survive
transport. `main.py` launches the actual server as a subprocess over stdio with the official client, calls
every tool against real files, and asserts:

- the tool list is exactly what you promised
- findings arrive with rule id, severity and line number
- the secret in the test file (`hunter2`) appears nowhere in the output
- a missing file, a `../` traversal and invalid YAML each produce `is_error` with a readable message

## Run It

```bash
python 07-mcp-wrapper-and-testing/main.py
```

To use it from Claude Code:

```bash
claude mcp add minilint -- python -m minilint.server --dir .
```

(Run it from this repository's root so `minilint` is importable.)

## Where to go from here

The full project, [dockerlint-mcp](https://github.com/0xmortuex/dockerlint-mcp), adds what this tutorial
skips: 28 Dockerfile rules, ONBUILD awareness in the rules, proper Windows path handling, redaction in
every output, a 16-file false-positive corpus, hostile-input tests (huge lines, nested YAML, alias bombs,
pathological patterns), multi-stage rewrite proposals, and a `.dockerignore` checker. The shape is the one
you just built.

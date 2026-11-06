# Module 03: Cache-Order Analysis

## The Concept

An image is a stack of layers. `RUN`, `COPY` and `ADD` create a layer holding filesystem changes;
`ENV`, `WORKDIR`, `USER`, `CMD` and friends only change metadata. Docker caches a layer by its parent, its
instruction text and, for `COPY`/`ADD`, a checksum of the copied files. **When one layer misses the cache,
every layer after it is rebuilt.**

So ordering is the whole game: put what changes rarely first, what changes on every commit last.

```dockerfile
COPY . .                                  # changes on every edit of any file
RUN pip install -r requirements.txt       # ...so this slow step re-runs every time
```

versus

```dockerfile
COPY requirements.txt .                   # changes only when dependencies change
RUN pip install -r requirements.txt       # cached across code edits
COPY . .
```

## What We Build

[`minilint/layers.py`](../minilint/layers.py):

- `is_dependency_install(cmd)`: recognises `pip install -r`, `npm ci`, `yarn install`, `go mod download`,
  `bundle install`. Note what it does *not* match: `pip install .` after `COPY . .` is a legitimate way to
  install the project itself.
- `copies_everything(ins)`: `COPY . .`, `COPY ./ /app`, `COPY * /app`. `COPY --from=...` is excluded: it
  copies build artifacts, not the build context.
- `explain(df)`: for each instruction, does it make a layer, and a heuristic size hint.
- Two rules registered with the engine from module 02:
  - **ML007** `COPY . ` before the dependency install, per stage.
  - **ML008** `RUN rm -rf ...` as its own layer. Layers are immutable: deleting files later *hides* them
    but the bytes stay in the earlier layer, so the image does not shrink.

## Size hints are hints

Nothing is built, so sizes are inferred from commands: OS package installs are "large", dependency
installs are "large", `COPY . .` is "the whole build context". The output says so. Overstating certainty
is worse than admitting the limit.

## The false-positive trap

A naive ML007 flags any `COPY .` that has *any* install somewhere after it. That fires on the correct
order whenever a later step installs the project itself. The `elif` in the loop prevents it: if a
dependency install is seen *before* the big copy, stop looking at that stage. Always test the good order.

## Run It

```bash
python 03-cache-order-analysis/main.py
```

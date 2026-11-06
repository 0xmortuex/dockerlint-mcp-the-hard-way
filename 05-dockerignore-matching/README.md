# Module 05: Dockerignore Matching

## The Concept

`.dockerignore` looks like `.gitignore` and behaves differently. Reimplementing it from memory of
gitignore gives wrong answers in exactly the cases that matter. Docker's rules:

| Behaviour | `.gitignore` | `.dockerignore` |
|-----------|--------------|-----------------|
| `node_modules` | matches at **any** depth | matches only at the **context root** |
| to match at any depth | `node_modules` | `**/node_modules` |
| `*` | does not cross `/` | does not cross `/` |
| `**` | crosses directories | crosses directories |
| last matching pattern wins | yes | yes |
| `!pattern` re-includes | yes (if parent not excluded) | yes |
| matching a directory excludes its contents | yes | yes |

The first row is the bug people ship: `node_modules` in `.dockerignore` does nothing for
`packages/app/node_modules` in a monorepo, so a gigabyte of host modules goes to the daemon.

## What We Build

[`minilint/dockerignore.py`](../minilint/dockerignore.py):

1. **`glob_to_regex`.** Translate a pattern one character at a time: `*` becomes `[^/]*`, `?` becomes
   `[^/]`, `**/` becomes `(?:.*/)?` (zero or more directories), everything else is `re.escape`d.
2. **`IgnoreMatcher.match(path)`.** Normalise the pattern (`./build`, `build/` and `/build` all mean
   `build`), then for each pattern in order test the path **and each of its parent directories**. The
   last pattern that matches decides, and `!` flips the decision. It also returns the *deciding pattern*
   and its line number.

That last part is what makes the tool useful to an agent. The check that matters is:

```python
ignore = IgnoreMatcher(".git\n*.txt\n")
[(p, ignore.match(p)[1].raw) for p in ["requirements.txt", "src/app.py"] if ignore.excludes(p)]
# [("requirements.txt", "*.txt")]
```

"Your `.dockerignore` line 2 (`*.txt`) removes `requirements.txt`, which the Dockerfile `COPY`s on line 5"
is a finding the model can fix in one edit. Without the line numbers it would have to guess.

## Safety note

Patterns come from files you do not control. Translating them to regexes means a hostile pattern such as
`*a*a*a*a*a*a...b` can make Python's `re` backtrack badly. The real project caps the number of wildcards per
pattern and the number of patterns, and reports a clear error instead of hanging.

## Run It

```bash
python 05-dockerignore-matching/main.py
```

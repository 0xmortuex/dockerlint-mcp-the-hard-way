# Module 01: Dockerfile Grammar

## The Concept

A Dockerfile looks like a list of lines. It is not. The grammar has a handful of rules, and a linter that
ignores any one of them gives wrong answers:

1. **Parser directives** (`# syntax=...`, `# escape=...`) are comments that are not comments, but only
   at the very top. Once any other line has been seen they are ordinary comments.
2. **Line continuations.** A trailing `\` joins the next line. Inside a continued instruction Docker
   silently *drops* comment lines and blank lines. So this is a single `RUN`:

   ```dockerfile
   RUN apt-get update \
       # a comment inside the instruction
       && apt-get install -y curl
   ```

3. **The escape character** can be changed to a backtick (Windows Dockerfiles), which changes what counts
   as a continuation.
4. **Heredocs.** `RUN <<EOF ... EOF` body lines are taken verbatim. A `#` line inside is script text,
   not a Dockerfile comment, and a line that *looks* like `FROM` inside it is not an instruction.
5. **Exec vs shell form.** `CMD ["python", "app.py"]` is a JSON array and runs without a shell;
   `CMD python app.py` runs under `/bin/sh -c`. An array with single quotes is *not* valid JSON, so
   Docker silently treats it as shell form: a classic bug a linter should catch.
6. **Flags** such as `--mount=...`, `--chown=...`, `--from=...`, `--platform=...` come before the arguments.
7. **Multi-stage.** Every `FROM` starts a stage; `FROM x AS name` names it; only `ARG`s before the first
   `FROM` can be used in `FROM`.
8. **ONBUILD** instructions are stored for *child* images; they do not run in this build.

## What We Build

[`minilint/parser.py`](../minilint/parser.py): `parse(text) -> Dockerfile`, with `Instruction`s that know
their first and last physical line, flags, form, heredoc bodies and ignore comments, plus `Stage`s.

The core is a loop over physical lines:

```python
while (m := continuation.search(piece)):
    parts.append(piece[: m.start()])          # keep the text before the backslash
    i += 1
    while i < n and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        ignores |= ignore_ids(lines[i].strip())  # comments inside are dropped, but may carry ignores
        i += 1
    piece = lines[i]
```

Then the keyword is split from the rest, flags are peeled off, JSON form is tried with `json.loads`
(anything that fails stays shell form, which is exactly Docker's behaviour), and heredocs consume the
lines that follow.

Two design decisions worth noticing:

- **Never raise on bad input.** Problems go into `Dockerfile.errors` with a line number; a linter that
  crashes on a half-typed file is useless to an agent that is editing it.
- **Keep both line numbers.** `line` and `end_line` let a finding point at the instruction's first line
  while an ignore comment can live anywhere inside it.

## Run It

```bash
python 01-dockerfile-grammar/main.py
```

`main.py` parses a deliberately nasty file and asserts each claim above: the comment inside the `RUN`, the
heredoc line numbers, flags, JSON form, `ARG` expansion into `FROM`, ONBUILD, and garbage input.

## Break It

- Remove the inner `while` that skips comments and rerun: the continued `RUN` ends at the comment line and
  the next line becomes a bogus instruction `&&`.
- Change `HEREDOC` so it also matches `<<<` (a here-string): `cat <<< hello` now swallows the rest of the
  file looking for a delimiter.

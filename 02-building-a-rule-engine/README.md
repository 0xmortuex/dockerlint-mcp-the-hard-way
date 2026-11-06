# Module 02: Building a Rule Engine

## The Concept

A rule is a function from a parsed Dockerfile to zero or more *hits*. The engine's job is everything
around that: run every enabled rule, honour suppressions, attach a severity, sort the output.

```python
@rule("ML002", "warning")
def apt_update_alone(df):
    for ins in runs(df):
        cmds = commands(ins)
        update = any(c[:2] == ["apt-get", "update"] for c in cmds)
        install = any(c[:2] == ["apt-get", "install"] for c in cmds)
        if update and not install:
            yield Hit(ins.line, "apt-get update in its own layer gets cached and goes stale.", "RUN apt-get update && apt-get install ...")
```

## Why rules read commands, not text

`RUN echo "apt-get update is only a string here" && apt-get install -y curl` contains the text
`apt-get update` but never runs it. A regex rule fires; a rule over **commands** does not. So the engine
includes `commands(ins)`, a tiny tokenizer that uses `shlex` with `punctuation_chars=True` to split on
`&&`, `||`, `;`, `|` and newlines while keeping quotes intact:

```python
commands(parse("FROM a:1\nRUN a && b 'c && d' | e ; f\n").instructions[1])
# [["a"], ["b", "c && d"], ["e"], ["f"]]
```

It is not a shell (no variable expansion, no subshell semantics), and that is fine: the question is only
"is this program invoked with this flag".

## Every finding has a fix

`Hit(line, message, fix)`: the `fix` field is not optional. An agent that reads "missing
`--no-install-recommends`" can act on it; one that reads "bloated image" has to guess.

## Secrets: report the name, never the value

Rule ML006 flags `ENV DB_PASSWORD=hunter2` but its message contains only `DB_PASSWORD`. The linter's output
goes into a model's context, and from there into logs and transcripts. A security linter that echoes the
secret it found is itself a leak. `main.py` asserts `"hunter2" not in message + fix`.

## Suppression and disabling

Two escape hatches, both essential because every rule has legitimate exceptions:

- **In the file:** `# minilint-ignore: ML001, ML004` on the lines above an instruction (or inside it). The
  parser already attached those ids to the instruction in module 01, so the engine only checks
  `rid in ins.ignores`.
- **In configuration:** the `disabled` set, wired to a `--disable` command-line flag in module 07.

## The false-positive guard

The most important test is not "does it find bad things", it is "does it stay silent on a good file".
`main.py` ends with a well-written Dockerfile that must produce zero findings. In the real project there
is a corpus of 16 realistic Dockerfiles with that exact assertion; whenever a rule produced a finding on
one of them, the rule was wrong, not the file.

## Run It

```bash
python 02-building-a-rule-engine/main.py
```

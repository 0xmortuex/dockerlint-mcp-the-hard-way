# Module 06: Fix Previews

## The Concept

Telling an AI "add `--no-install-recommends`" works. Handing it a **unified diff** it can apply (or show
you) works better. But a tool that edits files on its own is a different risk class, so the tool here only
*previews*: it returns text and writes nothing. The agent or the user applies it.

A preview is only worth showing if it is **safe and verified**:

1. **Only mechanical fixes.** Adding a flag to a command cannot change what the image does. Converting
   `CMD python app.py` to exec form can: shell form expands `$HOME`, pipes and globs; exec form does not.
   `fix_shell_form` therefore converts only when every word matches `[\w./:=@%+,-]+`.
2. **Never change the line count.** Fixes rewrite the physical lines of an instruction in place. Finding
   line numbers from before the fix stay valid for after it, and the diff stays small. `preview` asserts
   this.
3. **Verify by re-linting.** After applying fixes in memory, parse and lint the result and report how many
   findings remain. If a "fix" had introduced a problem, the count would show it.
4. **Say what is left.** The real tool lists findings with no safe automatic fix (pin the base image, add
   a `USER`, add a `HEALTHCHECK`) because they need a human decision.

## What We Build

[`minilint/fixes.py`](../minilint/fixes.py):

```python
FIXERS = {"ML003": fix_recommends, "ML005": fix_shell_form}

def preview(text, findings, df):
    original = text.splitlines()
    fixed = list(original)
    for f in findings:
        ins, fixer = df.instruction_at(f.line), FIXERS.get(f.rule)
        if ins and fixer and (f.rule, ins.line) not in done:
            if fixer(fixed, ins):
                done.add((f.rule, ins.line))
    ...
    diff = difflib.unified_diff(original, fixed, "a/Dockerfile", "b/Dockerfile", lineterm="")
```

A fixer takes the list of physical lines and the instruction, mutates the lines, and returns whether it
changed anything. Fixers are keyed by the rule they resolve, so a suppressed or disabled finding is never
"fixed": the preview is driven by the *findings*, not by pattern-matching the file again.

One wart to notice: the preview prints file contents. In the real server the diff is passed through the
same secret redactor as everything else, because a context line can contain `ENV DB_PASSWORD=...`.

## Run It

```bash
python 06-fix-previews/main.py
```

## Break It

Add `"ML006": remove_the_env_line` to `FIXERS`. It is tempting ("just delete the secret!") and wrong:
deleting the line changes what the image does and does not rotate the credential. Some findings should
stay manual.

# Module 04: Compose Analysis

## The Concept

A compose file is YAML, so parsing is easy and *locating* is hard. `yaml.safe_load` returns dicts and
lists; the line numbers are gone. An AI that is told "service `web` is privileged" still has to hunt for
it. We want "line 4".

## Always `safe_load`

`yaml.load` can construct arbitrary Python objects from tags such as `!!python/object/apply:os.system`.
A linter reads files from repositories it does not control, so it must use `yaml.safe_load`. `main.py`
proves it: feeding that tag raises a `YAMLError` instead of running a command.

## Getting line numbers back

`Locator` scans the text once to find each service block (the lines indented one level under `services:`),
then `find(service, regex)` searches only inside that block:

```python
loc.find("db", r"POSTGRES_PASSWORD")   # -> 12
```

If the key cannot be found (flow-style YAML, unusual formatting), it falls back to the service's own line.
That is a documented approximation, not a hidden failure: the finding is still correct, only less precise.

## The rules

| Rule | Why it matters |
|------|----------------|
| MC001 | `image: nginx` means `:latest`; the deploy changes when upstream does |
| MC002 | `privileged: true` removes almost all container isolation |
| MC003 | Mounting `docker.sock` hands out root on the host |
| MC004 | A secret in `environment:` is committed to git and visible in `docker inspect` |
| MC005 | `"8080:80"` publishes on **all** interfaces; `"127.0.0.1:8080:80"` does not |

MC005 shows why you read the structure, not the text: only a short port with exactly one `:` lacks a host IP.
`"127.0.0.1:5432:5432"` has two and is correctly ignored. As with module 02, environment values that start
with `$` (interpolations) are not secrets, and values are never echoed.

## Run It

```bash
python 04-compose-analysis/main.py
```

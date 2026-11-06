"""Module 05: .dockerignore is not .gitignore."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from minilint.dockerignore import IgnoreMatcher, glob_to_regex  # noqa: E402

# 1. Anchored at the context root.
m = IgnoreMatcher("node_modules\n")
assert m.excludes("node_modules") and m.excludes("node_modules/left-pad/index.js")
assert not m.excludes("packages/app/node_modules")  # .gitignore WOULD match this; Docker does not
assert IgnoreMatcher("**/node_modules\n").excludes("packages/app/node_modules/x.js")

# 2. `*` stays inside one path segment, `**` crosses them.
assert glob_to_regex("src/*.py").match("src/a.py") and not glob_to_regex("src/*.py").match("src/sub/a.py")
assert glob_to_regex("src/**/a.py").match("src/a.py") and glob_to_regex("src/**/a.py").match("src/x/y/a.py")
assert glob_to_regex("a?c").match("abc") and not glob_to_regex("a?c").match("a/c")

# 3. Excluding a directory excludes everything inside it.
assert IgnoreMatcher("docs\n").excludes("docs/guide/intro.md")

# 4. The last matching pattern wins, and `!` re-includes.
m = IgnoreMatcher("*.md\n!README.md\n")
assert m.excludes("CHANGELOG.md") and not m.excludes("README.md")
assert IgnoreMatcher("!README.md\n*.md\n").excludes("README.md")  # order matters

# 5. The deciding pattern and its line number are reported, so an AI can say WHICH line breaks a COPY.
excluded, pat = IgnoreMatcher("# comment\n\n*.txt\n").match("requirements.txt")
assert excluded and pat is not None and (pat.line, pat.raw) == (3, "*.txt")

# 6. `./x`, `x/` and `/x` all normalise to `x`.
for spelling in ("./build", "build/", "/build"):
    assert IgnoreMatcher(spelling + "\n").excludes("build/out.bin"), spelling

# 7. The check that matters most: does the ignore file break a COPY?
ignore = IgnoreMatcher(".git\n*.txt\n")
copied = ["requirements.txt", "src/app.py"]
broken = [(p, ignore.match(p)[1].raw) for p in copied if ignore.excludes(p)]
assert broken == [("requirements.txt", "*.txt")]

print("module 05 OK: root-anchoring, wildcards, negation and COPY conflicts behave like Docker")

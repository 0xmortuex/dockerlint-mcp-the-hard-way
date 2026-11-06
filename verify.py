"""Run every module's main.py, the way CI does. Each main.py checks its own results with assert;
a chapter whose code drifts from what its README claims fails here.

Usage: python verify.py            # all modules
       python verify.py 03 05      # just these
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    wanted = sys.argv[1:]
    modules = sorted(glob.glob(os.path.join(ROOT, "[0-9][0-9]-*", "main.py")))
    if wanted:
        modules = [m for m in modules if os.path.basename(os.path.dirname(m))[:2] in wanted]
    if not modules:
        print("no modules found")
        return 1
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    failed = []
    for path in modules:
        name = os.path.basename(os.path.dirname(path))
        proc = subprocess.run(
            [sys.executable, path], cwd=ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", timeout=180,
        )
        status = "ok  " if proc.returncode == 0 else "FAIL"
        last = (proc.stdout.strip().splitlines() or [""])[-1]
        print(f"{status} {name}: {last}")
        if proc.returncode != 0:
            failed.append(name)
            print(proc.stdout)
            print(proc.stderr)
    if failed:
        print("FAILED:", ", ".join(failed))
        return 1
    print(f"all {len(modules)} modules verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""18r31: 100 rounds per cell multi-thread matrix + pending recovery.
Does not overwrite 18r30 packages. Uses same API as matrix_18r30_multithread.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

ROOT = Path(r"C:\Users\zhang\grok-regkit")
SCRIPT = ROOT / "tools" / "matrix_18r30_multithread.py"

def main():
    rounds = 100
    workers = 2
    args = [sys.executable, "-B", str(SCRIPT), "--rounds", str(rounds), "--workers", str(workers)]
    # allow extra passthrough
    args += sys.argv[1:]
    print("18r31 launcher:", " ".join(args), flush=True)
    # stamp meta
    out = ROOT / "matrix_runs"
    out.mkdir(exist_ok=True)
    (out / "_matrix_18r31_meta.txt").write_text(
        f"tag=stable-2026-07-19-matrix-multithread-18r31-100rounds\nrounds={rounds}\nworkers={workers}\n",
        encoding="utf-8",
    )
    raise SystemExit(subprocess.call(args, cwd=str(ROOT)))

if __name__ == "__main__":
    main()

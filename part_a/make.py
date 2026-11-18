"""Cross-platform build driver.

Use `python make.py seed`. The Makefile and make.bat are thin wrappers
over this file for GNU make and Windows CMD/PowerShell.
"""
from __future__ import annotations

import os
import subprocess
import sys

PY = sys.executable
HELP = """make seed        Full rebuild (profile -> clean -> scales -> SQL -> verify)
make profile     Rebuild the profile and metrics only
make dictionary  Rebuild the column dictionary only
make clean-data  Run the cleaner only -> data/clean/
make scale       Rebuild the three scale tiers (FACTORS=1,5,10 supported)
make seed-sql    Rebuild sql/load_*.sql and data/manifest.json
make load        Load into PostgreSQL (needs DATABASE_URL and schema.sql)
make test        Unit tests + correctness verification
make verify      Correctness verification only
make demo        Print the before/after figures used in the video
make pack        Compress scale CSVs above 50 MB to .csv.gz
make unpack      Restore from .csv.gz
make help        Show this help"""


def pipeline(*args: str) -> list[str]:
    return [PY, "-m", "etl.pipeline", *args]


def run(cmd: list[str]) -> int:
    print("+ " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    return subprocess.call(cmd)


def main(argv: list[str]) -> int:
    if not argv:
        print(HELP)
        return 0
    target = argv[0]
    opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)

    if target == "help":
        print(HELP)
        return 0
    if target in {"seed", "all"}:
        return run(pipeline("all"))
    if target in {"mappings", "dictionary", "profile", "verify", "demo", "pack", "unpack",
                  "clean", "clean-data", "seed-sql"}:
        sub = {"clean": "clean", "clean-data": "clean", "seed-sql": "seed"}[target] \
            if target in {"clean", "clean-data", "seed-sql"} else target
        return run(pipeline(sub))
    if target == "scale":
        args = ["scale"] + (["--factors", opts["FACTORS"]] if "FACTORS" in opts else [])
        return run(pipeline(*args))
    if target == "test":
        rc = run([PY, "-m", "unittest", "discover", "-s", "tests", "-v"])
        return rc if rc else run(pipeline("verify"))
    if target == "load":
        url = opts.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
        if not url:
            print("Set DATABASE_URL, e.g. make load DATABASE_URL=postgres://user:pwd@localhost:5432/recipes")
            return 1
        return run(["psql", url, "-f", "sql/load_clean.sql"])
    print(f"Unknown target: {target}\n\n{HELP}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

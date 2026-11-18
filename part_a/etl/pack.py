"""Compress scale CSVs above 50 MB for GitHub, and restore them."""
from __future__ import annotations

import gzip
from pathlib import Path

from . import config as C
from . import io_utils as U

# GitHub warns above 50 MB and rejects above 100 MB
THRESHOLD = 50 * 1024 * 1024


def targets() -> list[Path]:
    return [p for p in C.SCALES.rglob("*.csv") if p.stat().st_size > THRESHOLD]


def pack(verbose: bool = True) -> list[dict[str, str]]:
    out = []
    for p in targets():
        gz = p.with_suffix(p.suffix + ".gz")
        # mtime=0 keeps the .gz reproducible; gzip.open has no mtime argument
        with open(p, "rb") as fi, gzip.GzipFile(filename=str(gz), mode="wb",
                                               compresslevel=6, mtime=0) as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)
        rec = {"csv": str(p.relative_to(C.ROOT)).replace("\\", "/"),
               "gz": str(gz.relative_to(C.ROOT)).replace("\\", "/"),
               "csv_bytes": p.stat().st_size, "gz_bytes": gz.stat().st_size,
               "ratio": f"{gz.stat().st_size / p.stat().st_size * 100:.1f}%",
               "sha256_gz": U.sha256(gz)}
        out.append(rec)
        if verbose:
            U.log(f"Packed {p.name}: {rec['csv_bytes'] / 1048576:.1f}MB -> "
                  f"{rec['gz_bytes'] / 1048576:.1f}MB ({rec['ratio']})")
    U.write_json(C.SCALES / "pack_manifest.json", {"threshold_bytes": THRESHOLD, "files": out})
    return out


def unpack(verbose: bool = True) -> int:
    n = 0
    for gz in C.SCALES.rglob("*.csv.gz"):
        p = gz.with_suffix("")           # strip .gz -> xxx.csv
        with gzip.open(gz, "rb") as fi, open(p, "wb") as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)
        n += 1
        if verbose:
            U.log(f"Restored {p.name} ({p.stat().st_size / 1048576:.1f}MB)")
    return n

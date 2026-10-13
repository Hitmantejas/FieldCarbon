"""Download the two open datasets behind fleet sites S2 and S3 and verify their checksums.

Both are CC BY 4.0 on Mendeley Data. Raw files go to data/raw/ (gitignored). The Tümosan archive is a
.rar: only the .tab data files and the README are extracted, with Windows' `tar` (bsdtar reads .rar), to
data/raw/tumosan/extracted. Nothing in the archive is executed.

Run: python data/prep/download_fleet.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "raw"
UA = {"User-Agent": "Mozilla/5.0 (FieldCarbon data prep)"}  # Mendeley refuses the default Python agent

FILES = [  # dataset id, version, file name, folder, expected sha256 (published by Mendeley)
    ("y3h5xzkjc6", 1, "Dataset.csv", "vineyard", "9d8d101eb286bbe9af1cf375f45de63677eff216524fe9672eaed6911efd3f28"),
    ("bbjtjrsxvx", 2, "FIELD_FILES.rar", "tumosan", "b967db43073985df5d0e6fb3cfc3ebf3d3c6d80c5833e69fbb99019fa4b557e5"),
]


def fetch(url: str) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(dataset: str, version: int, name: str, folder: str, expected: str) -> Path:
    dest = RAW / folder / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or sha256(dest) != expected:
        meta = json.loads(fetch(f"https://data.mendeley.com/public-api/datasets/{dataset}/files?folder_id=root&version={version}"))
        entry = next(f for f in meta if f["filename"] == name)
        dest.write_bytes(fetch(entry["content_details"]["download_url"]))
    if sha256(dest) != expected:
        raise SystemExit(f"{name}: checksum does not match the published value; not using it")
    print(f"{name}: ok ({dest.stat().st_size:,} bytes, sha256 verified)")
    return dest


def extract_tumosan(archive: Path) -> None:
    out = archive.parent / "extracted"
    if out.exists() and any(out.glob("FIELD_*_RAW.tab")):
        return
    tar = shutil.which("tar")
    out.mkdir(exist_ok=True)
    subprocess.run([tar, "-xf", str(archive), "-C", str(out), "--include=*.tab", "--include=README.txt"], check=True)
    print(f"extracted {len(list(out.glob('*.tab')))} .tab files and the README to {out}")


if __name__ == "__main__":
    for spec in FILES:
        path = download(*spec)
    extract_tumosan(RAW / "tumosan" / "FIELD_FILES.rar")

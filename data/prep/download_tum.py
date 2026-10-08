"""Download the TUM Agricultural Load Cycles zips from Zenodo into data/raw/ and verify md5.

Data: Götz, K. (2025), Zenodo, doi:10.5281/zenodo.14619787, CC-BY-4.0.
Usage: python data/prep/download_tum.py [--only "Fendt 211.zip"]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import requests

RECORD_API = "https://zenodo.org/api/records/14619787"
RAW_DIR = Path(__file__).resolve().parents[1] / "raw"


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_resumable(url: str, tmp: Path, size: int, retries: int = 8) -> None:
    """Download to `tmp`, resuming with HTTP Range after connection resets."""
    for attempt in range(1, retries + 1):
        have = tmp.stat().st_size if tmp.exists() else 0
        if have >= size:
            return
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(url, stream=True, timeout=600, headers=headers) as r:
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with tmp.open(mode) as out:
                    for block in r.iter_content(1 << 20):
                        out.write(block)
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError, requests.Timeout) as e:
            print(f"  attempt {attempt} interrupted at {tmp.stat().st_size / 1e6:.0f} MB: {type(e).__name__}")
            time.sleep(min(30, 2 ** attempt))
    if not tmp.exists() or tmp.stat().st_size < size:
        raise SystemExit(f"download incomplete after {retries} attempts: {tmp.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append", help="file name(s) to fetch; default all")
    args = ap.parse_args()

    record = requests.get(RECORD_API, timeout=60).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"record": RECORD_API, "revision": record.get("revision"),
                "licence": (record.get("metadata", {}).get("license") or {}).get("id"), "files": []}

    for f in record["files"]:
        name, expected = f["key"], f["checksum"].removeprefix("md5:")
        if args.only and name not in args.only:
            continue
        target = RAW_DIR / name
        if target.exists() and md5_of(target) == expected:
            print(f"ok (cached)  {name}")
        else:
            print(f"downloading  {name} ({f['size'] / 1e6:.0f} MB)")
            tmp = target.with_suffix(".part")
            fetch_resumable(f["links"]["self"], tmp, f["size"])
            if md5_of(tmp) != expected:
                tmp.unlink()
                raise SystemExit(f"md5 mismatch for {name}")
            tmp.replace(target)
        manifest["files"].append({"name": name, "md5": expected, "size": f["size"]})

    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"manifest -> {RAW_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()

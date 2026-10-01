#!/usr/bin/env python3
"""Stage the raw inputs into sources/ and write sources/MANIFEST.json.

GitHub sources are fetched at a pinned commit, so a re-stage reproduces the
same bytes. The two QUL files need a (free) QUL login to download, so they are
passed in as local paths:

    python scripts/stage_sources.py \
        --qul-phrases-zip  "~/Downloads/Mutashabihat ul Quran.json.bz2" \
        --qul-matching-zip ~/Downloads/matching-ayah.json.zip

Note the phrases download is a ZIP despite its .bz2 extension.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sources"

GITHUB = {
    "waqar": {
        "url": "https://github.com/Waqar144/Quran_Mutashabihat_Data.git",
        "sha": "f35f6d5d6e7d07f44e6a652d868b298fcd12e318",
        "files": ["mutashabiha_data.json", "README.md"],
        "license": "No formal license. README: free to use, attribution requested.",
    },
    "srmdn": {
        "url": "https://github.com/srmdn/quran-mutashabihat.git",
        "sha": "7a4cecb0e180625a862bd6886844a776d6c9cc7c",
        "files": ["pairs.json", "README.md"],
        "license": "Curated pairs CC BY 4.0; pending pairs (derived from Waqar) have no formal license.",
    },
    "furooq": {
        "url": "https://github.com/alinice1998/Furooq.git",
        "sha": "e1d933f5b7a31c7a9b281007f5219eb10ad1cc5f",
        "files": ["data/similarities.json", "data/quran.json", "LICENSE"],
        "license": "MIT",
    },
    # ilm only supplies QUL's QPC Hafs word text (and byte-identical copies of the
    # two QUL mutashabihat files, used as a cross-check). It adds no data of its own.
    "ilm": {
        "url": "https://github.com/arriqaaq/ilm.git",
        "sha": "a5192075cf08cabeb9f073a854218f5d7388f376",
        "files": ["qul/qpc-hafs.json", "qul/phrases.json", "qul/matching-ayah.json", "LICENSE"],
        "license": "Repo code Apache-2.0. The qul/ data files come from QUL; QUL data terms unconfirmed.",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(*cmd: str, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fetch_github(name: str, spec: dict) -> list[dict]:
    dest = SRC / name
    if dest.exists():
        shutil.rmtree(dest)
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        run("git", "init", "-q", cwd=repo)
        run("git", "remote", "add", "origin", spec["url"], cwd=repo)
        run("git", "fetch", "-q", "--depth", "1", "origin", spec["sha"], cwd=repo)
        run("git", "checkout", "-q", "FETCH_HEAD", cwd=repo)
        out = []
        for rel in spec["files"]:
            target = dest / Path(rel).name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo / rel, target)
            out.append({"path": f"{name}/{target.name}", "sha256": sha256(target), "bytes": target.stat().st_size})
    return out


def extract_zip(zip_path: Path, dest_name: str, wanted: list[str]) -> list[dict]:
    zip_path = zip_path.expanduser()
    if not zipfile.is_zipfile(zip_path):
        sys.exit(f"{zip_path} is not a ZIP archive")
    dest = SRC / "qul"
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    with zipfile.ZipFile(zip_path) as z:
        names = {Path(n).name: n for n in z.namelist()}
        for want in wanted:
            if want not in names:
                sys.exit(f"{want} not found in {zip_path} (has {sorted(names)})")
            target = dest / want
            target.write_bytes(z.read(names[want]))
            info = z.getinfo(names[want])
            out.append(
                {
                    "path": f"qul/{want}",
                    "sha256": sha256(target),
                    "bytes": target.stat().st_size,
                    "archive": zip_path.name,
                    "archive_sha256": sha256(zip_path),
                    "archive_member_mtime": "%04d-%02d-%02d" % info.date_time[:3],
                }
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qul-phrases-zip", required=True, type=Path)
    ap.add_argument("--qul-matching-zip", required=True, type=Path)
    args = ap.parse_args()

    SRC.mkdir(exist_ok=True)
    manifest: dict = {"staged_on": datetime.date.today().isoformat(), "sources": {}}

    for name, spec in GITHUB.items():
        print(f"fetching {name} @ {spec['sha'][:8]}")
        manifest["sources"][name] = {
            "upstream": spec["url"],
            "commit": spec["sha"],
            "license": spec["license"],
            "files": fetch_github(name, spec),
        }

    qul_files = extract_zip(args.qul_phrases_zip, "qul", ["phrases.json", "phrase_verses.json"])
    qul_files += extract_zip(args.qul_matching_zip, "qul", ["matching-ayah.json"])
    # QPC Hafs word text comes from the ilm copy of QUL's script file.
    shutil.copy2(SRC / "ilm" / "qpc-hafs.json", SRC / "qul" / "qpc-hafs.json")
    qul_files.append(
        {"path": "qul/qpc-hafs.json", "sha256": sha256(SRC / "qul" / "qpc-hafs.json"), "bytes": (SRC / "qul" / "qpc-hafs.json").stat().st_size, "via": "arriqaaq/ilm qul/qpc-hafs.json"}
    )
    manifest["sources"]["qul"] = {
        "upstream": "https://qul.tarteel.ai/resources/mutashabihat/73 (Mutashabihat ul Quran); matching-ayah from QUL's similar-ayah resource; qpc-hafs script from QUL",
        "license": "UNCONFIRMED. QUL code is MIT, but no data license was found on the resource pages.",
        "files": qul_files,
    }

    # Cross-check: ilm vendors the same QUL mutashabihat files; they must match the downloads.
    for fname in ("phrases.json", "matching-ayah.json"):
        a, b = sha256(SRC / "qul" / fname), sha256(SRC / "ilm" / fname)
        status = "identical" if a == b else "DIFFERENT"
        manifest["sources"]["qul"].setdefault("cross_checks", {})[f"{fname} vs arriqaaq/ilm copy"] = status
        print(f"{fname}: {status} to the ilm copy")

    (SRC / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print("wrote sources/MANIFEST.json")


if __name__ == "__main__":
    main()

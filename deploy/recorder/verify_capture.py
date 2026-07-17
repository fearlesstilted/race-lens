#!/usr/bin/env python3
"""CI gate: a capture branch may change one complete fixture triplet only."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--paths-only", action="store_true")
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    changed = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", f"origin/main...{args.head}"],
        check=True, text=True, stdout=subprocess.PIPE,
    ).stdout.splitlines()
    prefixes = {"backend/fixtures/"}
    if not changed or any(not any(path.startswith(prefix) for prefix in prefixes) for path in changed):
        raise SystemExit("capture branch contains a non-fixture change")
    names = [Path(path).name for path in changed]
    stems = {
        name.removesuffix(suffix)
        for name in names
        for suffix in (".positions.json", ".track.json", ".jsonl")
        if name.endswith(suffix)
    }
    if len(stems) != 1:
        raise SystemExit("capture branch must contain exactly one session")
    stem = stems.pop()
    expected = {
        f"backend/fixtures/{stem}.jsonl",
        f"backend/fixtures/{stem}.track.json",
        f"backend/fixtures/{stem}.positions.json",
    }
    if set(changed) != expected:
        raise SystemExit("capture branch must contain one fixture/track/positions triplet")
    if args.paths_only:
        print(stem)
        return
    from racelens.recorder.postprocess import validate_archive

    fixtures = root / "backend" / "fixtures"
    report = validate_archive(
        fixtures / f"{stem}.jsonl",
        fixtures / f"{stem}.track.json",
        fixtures / f"{stem}.positions.json",
    )
    print(report.summary)


if __name__ == "__main__":
    main()

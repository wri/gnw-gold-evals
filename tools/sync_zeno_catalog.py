"""Snapshot project-zeno's dataset catalog for coverage reporting.

The agent repo (wri/project-zeno) defines every dataset the agent can use in
``src/agent/datasets/catalog/*.yml``: dataset ids, dataset-specific
parameters (e.g. ``canopy_cover``), context layers, and the four per-dataset
instruction fields. COVERAGE.md reports case coverage against that catalog,
but must stay regenerable offline (CI runs ``coverage_doc.py --check`` with
no sibling checkout), so this tool commits a trimmed snapshot and
``coverage_doc.py`` reads only the snapshot:

    uv run python tools/sync_zeno_catalog.py             # fetch origin/main, write cases/zeno_catalog.json
    uv run python tools/sync_zeno_catalog.py --no-fetch  # use origin/main as already fetched

Files are read via ``git show <ref>:<path>`` so the project-zeno working
tree is never touched. After a sync, regenerate the doc:

    uv run python tools/coverage_doc.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

CATALOG_PATH = "src/agent/datasets/catalog"

# the per-dataset behaviour contracts; order is the canonical reporting order
INSTRUCTION_FIELDS = (
    "prompt_instructions",
    "selection_hints",
    "code_instructions",
    "presentation_instructions",
)


def snapshot_entry(raw: dict, source_name: str) -> dict:
    """Trim one catalog YAML to the fields coverage reporting needs."""
    missing = [k for k in ("dataset_id", "dataset_name") if raw.get(k) is None]
    if missing:
        raise ValueError(f"{source_name}: catalog entry missing {', '.join(missing)}")
    try:
        parameters = [
            {"name": p["name"], "values": p.get("values") or []}
            for p in raw.get("parameters") or []
        ]
        context_layers = [layer["value"] for layer in raw.get("context_layers") or []]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{source_name}: malformed parameters/context_layers: {exc}")
    return {
        "dataset_id": str(raw["dataset_id"]),
        "dataset_name": str(raw["dataset_name"]),
        "parameters": parameters,
        "context_layers": context_layers,
        "instructions": [
            f for f in INSTRUCTION_FIELDS if str(raw.get(f) or "").strip()
        ],
    }


def sort_datasets(entries: list[dict]) -> list[dict]:
    """Numeric dataset ids first in numeric order, then any others lexically."""

    def key(entry: dict) -> tuple:
        raw = str(entry["dataset_id"])
        return (0, int(raw), "") if raw.isdigit() else (1, 0, raw)

    return sorted(entries, key=key)


def git(zeno: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(zeno), *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed in {zeno}:\n{result.stderr.strip()}"
        )
    return result.stdout


def build_snapshot(zeno: Path, ref: str, fetch: bool) -> dict:
    if fetch and ref.startswith("origin/"):
        git(zeno, "fetch", "origin", ref.removeprefix("origin/"))
    sha = git(zeno, "rev-parse", ref).strip()
    repo = git(zeno, "remote", "get-url", "origin").strip()
    files = [
        f for f in git(zeno, "ls-tree", "-r", "--name-only", ref, CATALOG_PATH).split()
        if f.endswith((".yml", ".yaml"))
    ]
    if not files:
        raise SystemExit(f"no catalog files under {CATALOG_PATH} at {ref}")
    entries = []
    for f in files:
        raw = yaml.safe_load(git(zeno, "show", f"{ref}:{f}"))
        entries.append(snapshot_entry(raw, f))
    return {
        "source": {
            "repo": repo,
            "ref": ref,
            "sha": sha,
            "path": CATALOG_PATH,
            "synced": date.today().isoformat(),
        },
        "datasets": sort_datasets(entries),
    }


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zeno", type=Path, default=repo_root.parent / "project-zeno",
                        help="path to a project-zeno checkout (default: sibling dir)")
    parser.add_argument("--ref", default="origin/main",
                        help="git ref to snapshot (default: origin/main)")
    parser.add_argument("--out", type=Path,
                        default=repo_root / "cases" / "zeno_catalog.json")
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip `git fetch`; snapshot the ref as-is")
    args = parser.parse_args()

    if not (args.zeno / ".git").exists():
        raise SystemExit(f"{args.zeno} is not a git checkout — pass --zeno")
    snapshot = build_snapshot(args.zeno, args.ref, fetch=not args.no_fetch)
    args.out.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    src = snapshot["source"]
    print(f"wrote {args.out}: {len(snapshot['datasets'])} datasets "
          f"@ {src['sha'][:7]} ({src['ref']})")
    print("now regenerate: uv run python tools/coverage_doc.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

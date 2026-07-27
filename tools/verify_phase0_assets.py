#!/usr/bin/env python3
"""Verify checkpoint paths and hashes recorded by the Phase 0 inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = PROJECT_ROOT / "models/model_inventory.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when an inventory entry is still waiting for its checkpoint path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory_path = args.inventory.expanduser().resolve()
    inventory = json.loads(inventory_path.read_text())
    project_root = inventory_path.parents[1]
    failed = False

    for model in inventory["models"]:
        artifacts = model["artifacts"]
        if not artifacts:
            print(f"PENDING {model['id']}: {model['status']}")
            failed = failed or args.strict
            continue

        for artifact in artifacts:
            path = (project_root / artifact["path"]).resolve()
            if not path.is_file():
                print(f"MISSING {model['id']} [{artifact['role']}]: {path}")
                failed = True
                continue
            actual = sha256_file(path)
            if actual != artifact["sha256"]:
                print(f"HASH_MISMATCH {model['id']} [{artifact['role']}]: {path}")
                failed = True
                continue
            print(f"OK {model['id']} [{artifact['role']}]: {path}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

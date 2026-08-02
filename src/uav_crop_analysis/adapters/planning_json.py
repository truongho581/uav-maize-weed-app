"""Atomic filesystem persistence for versioned GreenEye mission plans."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from uav_crop_analysis.errors import PersistenceError
from uav_crop_analysis.planning import PlannedMission
from uav_crop_analysis.planning.serialization import plan_from_dict, plan_to_dict


class JsonMissionPlanRepository:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, plan: PlannedMission) -> None:
        destination = self._path(plan.mission_id)
        temporary = self.root / f".{destination.name}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(
                json.dumps(
                    plan_to_dict(plan),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise PersistenceError(
                "cannot persist mission plan",
                context={"mission_id": plan.mission_id},
            ) from exc

    def get(self, mission_id: str) -> PlannedMission | None:
        source = self._path(mission_id)
        if not source.is_file():
            return None
        return self._read(source)

    def delete(self, mission_id: str) -> None:
        try:
            self._path(mission_id).unlink(missing_ok=True)
        except OSError as exc:
            raise PersistenceError(
                "cannot delete mission plan",
                context={"mission_id": mission_id},
            ) from exc

    def list(self) -> tuple[PlannedMission, ...]:
        return tuple(
            sorted(
                (self._read(path) for path in self.root.glob("*.plan.json")),
                key=lambda plan: plan.mission_id,
            )
        )

    def _read(self, source: Path) -> PlannedMission:
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("plan root must be an object")
            return plan_from_dict(value)
        except (OSError, ValueError, TypeError) as exc:
            raise PersistenceError(
                "cannot read persisted mission plan",
                context={"path": str(source)},
            ) from exc

    def _path(self, mission_id: str) -> Path:
        normalized = mission_id.strip()
        if not normalized:
            raise PersistenceError("mission_id must not be empty")
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return self.root / f"{digest}.plan.json"

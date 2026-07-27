"""Official PyODM client adapter for NodeODM orthomosaic processing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from uav_crop_analysis.errors import GeospatialError
from uav_crop_analysis.geospatial.ports import ProgressCallback


class NodeOdmOrthomosaicEngine:
    def __init__(
        self,
        node_url: str,
        *,
        timeout: int = 30,
        options: dict[str, object] | None = None,
        node_factory: Callable[[str, int], Any] | None = None,
    ) -> None:
        self.node_url = node_url
        self.timeout = timeout
        self.options = options or {
            "auto-boundary": True,
            "feature-quality": "high",
            "matcher-neighbors": 8,
            "orthophoto-resolution": 1.0,
        }
        self._node_factory = node_factory

    @property
    def public_node_url(self) -> str:
        parts = urlsplit(self.node_url)
        hostname = parts.hostname or ""
        if ":" in hostname:
            hostname = f"[{hostname}]"
        host = f"{hostname}:{parts.port}" if parts.port is not None else hostname
        return urlunsplit((parts.scheme, host, parts.path, "", ""))

    def create(
        self,
        mission_id: str,
        image_paths: tuple[Path, ...],
        output_dir: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> tuple[Path, dict[str, object]]:
        if len(image_paths) < 2:
            raise GeospatialError("NodeODM requires at least two source images")
        missing = [str(path) for path in image_paths if not path.is_file()]
        if missing:
            raise GeospatialError(f"NodeODM source images are missing: {missing[0]}")
        try:
            node = self._make_node()
            task = node.create_task(
                [str(path) for path in image_paths],
                self.options,
                name=mission_id,
                progress_callback=(
                    (lambda value: progress(float(value) / 100.0, "upload"))
                    if progress
                    else None
                ),
            )

            def status_callback(info: Any) -> None:
                if progress is not None:
                    value = float(getattr(info, "progress", 0.0)) / 100.0
                    progress(value, str(getattr(info, "status", "running")))

            task.wait_for_completion(status_callback=status_callback)
            destination = Path(task.download_assets(str(output_dir))).resolve()
        except GeospatialError:
            raise
        except Exception as exc:
            raise GeospatialError(f"NodeODM task failed: {exc}") from exc
        candidates = tuple(destination.rglob("odm_orthophoto.tif"))
        if len(candidates) != 1:
            raise GeospatialError(
                "NodeODM result does not contain exactly one odm_orthophoto.tif"
            )
        if progress is not None:
            progress(1.0, "downloaded")
        return candidates[0], {
            "engine": "NodeODM",
            "node_url": self.public_node_url,
            "task_id": str(task.uuid),
            "options": dict(self.options),
            "source_image_count": len(image_paths),
        }

    def _make_node(self) -> Any:
        if self._node_factory is not None:
            return self._node_factory(self.node_url, self.timeout)
        try:
            from pyodm import Node
        except ImportError as exc:
            raise GeospatialError("PyODM is required for NodeODM processing") from exc
        return Node.from_url(self.node_url, timeout=self.timeout)

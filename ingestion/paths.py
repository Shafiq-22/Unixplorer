"""Filesystem layout of the data snapshot (CLAUDE.md §4, §8.2)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """Return ATLAS_ROOT if set, else the nearest ancestor holding pyproject.toml."""
    env = os.environ.get("ATLAS_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
            return candidate
    raise FileNotFoundError("could not locate repo root (no pyproject.toml + data/ found)")


@dataclass(frozen=True)
class Layout:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def manifest(self) -> Path:
        return self.data / "manifest.yaml"

    @property
    def queries(self) -> Path:
        return self.data / "queries"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def landmarks(self) -> Path:
        return self.root / "ingestion" / "landmarks.yaml"

    def rel(self, path: Path) -> str:
        """Repo-relative POSIX path, as stored in the manifest."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

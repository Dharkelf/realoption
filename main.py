"""CLI entry point for the realoption project.

Kept intentionally thin (per AGENTS.md: "no business logic in main.py") — it only
wires together the modules under `src/`. All the actual work (fetching, merging,
saving) lives in `src/data_collection/pipeline.py::run()`.
"""

from __future__ import annotations

from src.data_collection.pipeline import run

if __name__ == "__main__":
    run()

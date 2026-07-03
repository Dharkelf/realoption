# realoption

## Overview

Collection of independent real-options / derivative-pricing mini-projects. Each result is
a self-contained, reproducible valuation model (binomial lattices, Monte Carlo simulation,
closed-form threshold models, etc.), inspired by — but not copied from — reference course
material kept locally only (see `AGENTS.md`, section "`local/` Directory — Never Synced").

Mini-projects are added incrementally; this README is updated in the same commit as each one.

## Architecture

```
config/settings.yaml ──► src/<module>/ ──► results/<name>.py ──► (optional) jupytext ──► .ipynb
                              │
                              ▼
                          tests/test_<module>.py
```

No modules exist yet — this section is filled in as mini-projects are scoped.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit install   # once .pre-commit-config.yaml exists
```

## Configuration

`config/settings.yaml` is currently empty — populated as the first mini-project is defined.

## Usage

No `results/*.py` scripts yet. Once added, run standalone:

```bash
python results/<name>.py
```

Convert a result to a notebook:

```bash
jupytext --to notebook results/<name>.py
```

## Data

No persisted data yet.

## Development

```bash
pytest tests/
pre-commit run --all-files
```

## Known Limitations

Project scaffolding only — no mini-projects implemented yet.

## Future Improvements

- First mini-project (to be scoped by the user).

## References

- See `AGENTS.md` for full project conventions.

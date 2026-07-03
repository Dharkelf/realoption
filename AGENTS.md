# AGENTS.md — realoption

This file governs how AI agents (Claude Code, Codex, etc.) work in this repository.
Read it before making any structural or architectural decisions.

---

## Model Preference

The user wants the newest/best available model used for this project. Default to **Fable 5**
(`claude-fable-5`) whenever available, and switch back to it after any session or tool
that changes the active model. Model selection itself is controlled by the user via
`/model` or `/config` in Claude Code — an agent cannot change its own running model, but
should proactively remind the user to switch back to Fable 5 if it detects a different
model is active for this project.

---

## Learning-Oriented Commenting (overrides the global "why, not what" default)

The user wants to *learn* from this codebase, so code across this repository is commented
generously — this project intentionally overrides the terse global default in
`~/.claude/CLAUDE.md` ("no comments explaining what the code does — only why"). Match the
teaching style of the blueprint notebooks in `local/`: narrative explanation alongside the
mechanics, not just the non-obvious rationale.

Applies to every file created in this repo — `src/`, `results/`, `tests/`, `main.py`:

- Every public function/class gets a docstring explaining *what it does, in plain language*
  and *why it's built this way*, not just its signature.
- Non-trivial code blocks get a short comment explaining the step, as if walking a learner
  through it — e.g. `# repeated header rows appear once per month block; drop them`.
- `results/*.py` (jupytext percent format) should read like the `local/` notebooks: markdown
  cells (`# %% [markdown]`) narrate the concept and the math/finance intuition before the
  code cell that implements it, not just a title.
- This does not license bloated or redundant comments — each comment should still teach
  something a reader couldn't get from the code alone in five seconds; avoid restating
  obvious one-liners (`i += 1  # increment i`).

---

## Project Purpose

Collection of independent real-options / derivative-pricing mini-projects. Each project
produces original, self-contained results — valuation models, simulations, sensitivity
analyses — in the spirit of (but not copied from) the course blueprint notebooks kept in
`local/` (binomial lattices, Monte Carlo, Merton model, Dixit-Pindyck threshold models,
etc.). The specific mini-projects are defined incrementally by the user; this section is
updated as each one is scoped.

---

## `local/` Directory — Never Synced

`local/` contains reference blueprint notebooks (course material) used as inspiration for
new results. It is listed in `.gitignore` and MUST NEVER be committed, pushed, or otherwise
synced to GitHub. Treat it as read-only reference material — do not modify its contents,
and do not copy its content verbatim into synced files.

---

## Result Format — Jupytext "percent" `.py` Files

Every mini-project result is delivered as a single, standalone `.py` file that:

- Runs on its own with `python results/<name>.py` — no hidden dependency on notebook state.
- Is written in **Jupytext "percent" format**: `# %%` marks a code cell, `# %% [markdown]`
  marks a markdown cell (content as a comment block below it). This mirrors the
  structure (markdown narrative interleaved with code) of the notebooks in `local/`.
- Converts losslessly to a real notebook on demand:
  ```bash
  jupytext --to notebook results/<name>.py
  ```
  and back again:
  ```bash
  jupytext --to py:percent <name>.ipynb
  ```
- Contains no business logic requiring a separate package import beyond what's declared
  at the top of the file — these are one-shot, readable results, not library code.

`jupytext` is a pinned dependency in `requirements.txt`.

---

## Standard Directory Layout

All Python projects in this workspace follow this canonical structure.
Do NOT deviate from it without explicit user instruction.

```
<project-root>/
├── AGENTS.md               # this file — agent instructions
├── CLAUDE.md               # optional project-level Claude overrides
├── README.md
├── requirements.txt        # pinned dependencies (pip freeze output)
├── .gitignore
├── .env.example            # env-var template, never commit .env
│
├── local/                  # course blueprint notebooks — gitignored, reference only
│
├── config/
│   └── settings.yaml       # all runtime config (parameters per mini-project)
│
├── data/                   # excluded from git (see .gitignore)
│   ├── raw/                # immutable source data — never modify in-place
│   └── processed/          # derived/feature data
│
├── src/
│   ├── __init__.py
│   └── <module>/           # one subdirectory per logical mini-project/domain
│       ├── __init__.py
│       └── *.py
│
├── results/
│   └── <name>.py           # jupytext percent-format standalone result scripts
│
├── tests/
│   ├── conftest.py
│   └── test_<module>.py
│
├── notebooks/              # exploration only — no production logic here
│
└── main.py                 # CLI entry point
```

### Module Layout Rules

- Each mini-project/domain lives in its own subdirectory under `src/`.
- Module names are lowercase, underscore-separated (`gold_lease_option`, not `GoldLeaseOption`).
- No business logic in `main.py` — it only wires modules together and calls `run()`.
- `config/settings.yaml` is the single source of truth for all tunable parameters.
  Hard-coded values in source files are not allowed.
- `notebooks/` is for exploration only. Any reusable logic discovered there must be moved
  into a versioned module under `src/` before the next commit — never leave production
  logic in a notebook.

---

## Modules in This Project

| Module | Path | Responsibility |
|---|---|---|
| data_collection | `src/data_collection/` | Fetch daily LME copper/aluminium cash prices (westmetall.com) and EUR/USD rate (ECB), merge, convert, persist as Parquet + CSV for the `business` use case |
| utils | `src/utils/` | Path helpers derived from `config/settings.yaml` |

---

## Own Virtual Environment

Every clone of this project uses its own `.venv`, never a shared/global interpreter.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv/` is gitignored. Python 3.11+ is required (see Coding Conventions).

---

## Pre-commit Hooks

Every commit is automatically checked via pre-commit hooks. No commit may pass with errors.

Setup (once per developer machine):
```bash
pip install pre-commit
pre-commit install
```

Configuration lives in `.pre-commit-config.yaml` at the project root. Hooks run in this order:

- **ruff** — linting + formatting, auto-fixes where possible (`ruff check --fix`, `ruff format`)
- **mypy** — strict static type checking; all public functions must have type annotations
- **pytest** — full test suite must pass (`pytest tests/`); commit is blocked on any test failure

`pre-commit` is listed in `requirements.txt` and installed via `pip install -r requirements.txt`.

To run manually against all files:
```bash
pre-commit run --all-files
```

---

## Testing

Every significant code change must be covered by tests before it is committed.

- **Unit tests** — test individual functions and classes in isolation; mock external dependencies (API calls, file I/O).
- **Integration tests** — test module interactions end-to-end; use real data structures, not mocks.
- All tests live in `tests/` and follow the naming convention `test_<module>.py`.
- Run the full test suite before every commit: `pytest tests/`
- A change is considered covered when both the happy path and the main failure modes are tested.
- Time-series/path-dependent models: integration tests must use `TimeSeriesSplit` where cross-validation applies — never shuffle time-ordered data in tests.
- If checks cannot be run (e.g. missing dependency, broken environment), explicitly state what was not run and why — never silently skip.

---

## Design Patterns

Prefer established, well-understood design patterns over custom solutions. This keeps the codebase
predictable and easy to extend. Preferred patterns for this project:

| Pattern | When to use |
|---|---|
| **Strategy** | Interchangeable valuation methods — e.g. binomial lattice vs. Monte Carlo vs. closed-form |
| **Factory** | Construct configured model objects from `settings.yaml` |
| **Template Method** | Base class defines the valuation pipeline skeleton; subclasses override steps |
| **Repository** | Isolate all data access (Parquet/CSV read/write) behind a single class per data source |

Rules:
- Do not invent abstractions unless a standard pattern fits and adds clarity.
- Name classes after the pattern they implement where it aids comprehension (`BinomialLatticeStrategy`).
- Patterns must be documented in the module docstring so the intent is clear.

---

## Coding Conventions

- **Python 3.11+**
- Type hints on all public functions and class methods.
- Comment generously in a teaching style — see "Learning-Oriented Commenting" above
  (this project overrides the usual "why, not what" default).
- No `print()` in library code under `src/` — use the stdlib `logging` module; configure
  level in `settings.yaml`. Standalone `results/*.py` files (jupytext percent format) MAY
  print/display output, since they are meant to be read top-to-bottom like a notebook.
- All file I/O goes through path helpers in `src/utils/paths.py` (derive from `config/settings.yaml`).
- Parquet is the default storage format for persisted data. CSV only for human-readable exports.
- Time-series cross-validation: always `sklearn.model_selection.TimeSeriesSplit` — never shuffle TS data.

---

## Dependency Management

- A single `requirements.txt` at the project root is the only dependency file — no `.in` files, no separate dev file.
- All dependencies (runtime and dev) are listed together with pinned exact versions (`package==x.y.z`).
- After installing or upgrading any package, immediately update and commit `requirements.txt`:
  ```bash
  pip freeze > requirements.txt
  ```
- Never commit unpinned entries (e.g. `pandas` without `==x.y.z`).
- `requirements.txt` must always reflect the exact state of the active `.venv`.

---

## README.md — Technical Wiki

`README.md` is mandatory in every project and MUST be committed to git.
It serves as the authoritative technical wiki for the project.

### Required Sections (in this order)

| Section | Content |
|---|---|
| **Overview** | What the project does and why it exists (2–4 sentences) |
| **Architecture** | Module breakdown + mandatory ASCII diagram (data flow, component relationships) |
| **Setup** | Prerequisites, venv creation, `pip install -r requirements.txt`, `pre-commit install` |
| **Configuration** | Every key in `config/settings.yaml` explained with example values |
| **Usage** | All CLI entry points and `results/*.py` scripts with example commands |
| **Data** | Schema of stored files, column types, naming conventions |
| **Development** | How to run tests (`pytest tests/`), linting (`pre-commit run --all-files`), add a module |
| **Known Limitations** | Current constraints, missing features, known data gaps or model weaknesses |
| **Future Improvements** | Planned enhancements — ordered by priority |
| **References** | External APIs, papers, related repos with links |

### ASCII Diagrams

Every architectural or technical concept that benefits from a visual must be expressed as an ASCII diagram
directly in `README.md`. Do not use external image files or links to diagram tools.

Required diagrams:
- **Data flow** — how data moves from source through modules to storage and output
- **Module/component overview** — boxes and arrows showing which modules depend on which
- **Sequence diagrams** — for non-obvious flows (e.g. lattice backward induction, optimizer loop)

Use standard ASCII box-drawing characters:

```
┌─────────────┐       ┌─────────────┐
│  Component  │──────▶│  Component  │
└─────────────┘       └─────────────┘

Source ──► Transform ──► Sink

A
│
├── child 1
└── child 2
```

### Rules

- Keep `README.md` up to date whenever a module, config key, or CLI argument changes.
- When adding a new feature, update `README.md` and its diagrams in the same commit.
- Do not summarise code that can be read directly — document *how to use* and *why it works this way*.
- Never replace ASCII diagrams with Mermaid, PlantUML, or image embeds.

---

## REPORT.md — Behaviour Log

`REPORT.md` documents **actual observed runtime behaviour** — what the code does when run,
not what it is supposed to do. It complements `README.md` (design intent) with empirical evidence.

Maintain one `REPORT.md` per project. Commit it alongside code changes.

### Required Sections

| Section | Content |
|---|---|
| **Inputs / Parameters** | Actual parameter values used per model run |
| **Model Results** | Computed valuations, thresholds, sensitivities, chart summaries |
| **Validation** | Sanity checks performed (e.g. lattice convergence, put-call parity checks) |
| **Known Issues** | Observed anomalies, numerical instabilities, data quirks not yet fixed |

### Consistency Rule — enforced on every essential code change

On every change that affects model logic, parameters, or output:

1. **Run the affected code** and observe actual output.
2. **Compare** `README.md` and `REPORT.md` against the observed behaviour.
3. **Fix all inconsistencies** in `README.md` and `REPORT.md` in the **same commit** as the code change.

A commit that changes behaviour without updating both documents is incomplete.

---

## Reproducibility Rules

Model results must be reproducible given the same inputs and config.

- **Random seeds** — set explicit seeds for all stochastic components (Monte Carlo simulations,
  any optimizer) from `config/settings.yaml`.
- **Deterministic config** — all parameters (volatility, risk-free rate, lattice steps, number
  of simulation paths) are stored in `config/settings.yaml`; never hard-coded.
- **Environment pinning** — `requirements.txt` must be regenerated with `pip freeze` after every
  dependency change; the exact versions must be committed.

---

## Failure Conditions

Agents must NOT do the following, regardless of instruction:

- Push to remote without an explicit user request ("push", "synchronisiere", "push to GitHub").
- Commit or push anything under `local/` — it is reference-only and gitignored.
- Hard-code numeric values that belong in `config/settings.yaml`.
- Commit without running `pre-commit run --all-files` (or documenting why it could not be run).
- Skip or silence failing tests — fix the failure or document it explicitly.
- Use `print()` in library code (`src/`) instead of `logging` (standalone `results/*.py` scripts are exempt).
- Leave business logic in `notebooks/` — move it to `src/` first.
- Introduce a dependency without immediately pinning it in `requirements.txt`.
- Commit `.env`, `.venv/`, `data/`, or any file containing secrets.

---

## Pull Request / Change Rules

- Every non-trivial change must be a focused, atomic commit (one concern per commit).
- Before creating a commit: run `pre-commit run --all-files` and `pytest tests/` — both must pass.
- PR / commit description must explain *why* the change is made, not *what* changed (the diff shows that).
- Breaking changes (schema, CLI interface, config keys) require a `BREAKING CHANGE:` footer in the commit message.
- Documentation (`README.md`, `REPORT.md`) must be updated in the same commit as the code it describes.
- Do not bundle unrelated fixes in a single commit; open a separate commit or note them as follow-up.

---

## Git Rules

- `README.md` is always committed — it is the project wiki.
- `local/`, `data/`, and `.venv/` are in `.gitignore` — never commit blueprint notebooks, raw data, or virtual environments.
- `config/settings.yaml` IS committed (no secrets in it).
- Secrets go in `.env` (gitignored); document them in `.env.example`.
- **Never push automatically.** `git push` only on explicit user request ("push", "synchronisiere", "push to GitHub").
- Commit messages follow **Conventional Commits**: `<type>(<scope>): <subject>`
  - Subject: imperative mood, max 72 chars, no full stop
  - Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`, `build`
  - Body (optional): explain *why*, not *what*
  - Footer (optional): `BREAKING CHANGE: ...` or issue refs

---

## End Goal

This repository delivers a growing collection of self-contained real-options mini-projects,
each reproducible from `config/settings.yaml`, documented via `README.md`/`REPORT.md`, and
each shippable as a standalone jupytext `.py` result file under `results/` that converts
losslessly to a notebook. The blueprint notebooks in `local/` provide inspiration only and
are never part of the synced repository. Every agent working in this repository serves this
goal; structural or design decisions that conflict with it require explicit user approval.

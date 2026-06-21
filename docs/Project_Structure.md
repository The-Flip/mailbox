# Project Structure

```text
mailbox/
├── mailbox/                # The application package (importable as `mailbox`)
│   ├── __init__.py
│   ├── config.py           # Environment-backed settings — the only reader of env vars
│   └── kit/                # Kit v4 API client
│       ├── __init__.py
│       ├── client.py       # KitClient: typed wrapper over httpx
│       └── errors.py       # KitAPIError hierarchy
├── tests/                  # pytest suite (mocks HTTP; no live calls by default)
│   ├── __init__.py
│   └── test_client.py
├── scripts/                # Dev/build scripts
│   ├── build_agent_docs.py     # Generates CLAUDE.md / AGENTS.md from docs/AGENTS.src.md
│   └── check_agent_docs_edit.sh
├── docs/                   # Developer documentation (this folder)
│   └── AGENTS.src.md       # Source for the generated agent docs
├── .claude/                # Claude Code config: agents, skills, commands, settings
├── .github/workflows/      # CI
├── CLAUDE.md / AGENTS.md   # GENERATED — do not edit directly
├── pyproject.toml          # Project metadata + tool config (ruff, mypy, pytest, coverage)
└── Makefile                # Common commands (wrap `uv run ...`)
```

## Conventions

- **Where code goes**
  - Anything that talks to Kit over HTTP lives under `mailbox/kit/`. Don't make HTTP calls elsewhere.
  - Configuration and secret access lives in `mailbox/config.py`. Don't read `os.environ` or `decouple.config` anywhere else.
  - Reusable helpers shared across modules get their own module — never dump them in `__init__.py`.
  - Higher-level mailing-list workflows get their own module(s) under `mailbox/` (e.g. `mailbox/lists.py`, `mailbox/broadcasts.py`) as they appear.
- **One responsibility per module.** Keep `client.py` about HTTP/transport concerns; keep business logic and safety checks in the workflow modules that call it.
- **Tests mirror the package.** A module `mailbox/kit/client.py` is tested by `tests/test_client.py`. Tests never hit the live API unless marked `@pytest.mark.integration` (see [Testing.md](Testing.md)).
- **Scripts are not part of the package.** Files in `scripts/` are standalone (run via `uv run python scripts/...`) and may use `print`.

## Generated files

`CLAUDE.md` and `AGENTS.md` are generated from `docs/AGENTS.src.md` by `scripts/build_agent_docs.py`. Edit the source, then run `make agent-docs`. A pre-commit hook regenerates them and blocks direct edits.

# Development Guide

The development documentation for Mailbox, The Flip's mailing-list management app.

- **[CONTRIBUTING.md](../CONTRIBUTING.md)** — Contribution workflow (branches, PRs, quality checks)
- **[Architecture.md](Architecture.md)** — System components and how they fit together
- **[Project_Structure.md](Project_Structure.md)** — Directory layout and where code goes
- **[KitAPI.md](KitAPI.md)** — Working with the Kit (kit.com) v4 API: auth, endpoints, pagination, rate limits, safety
- **[Python.md](Python.md)** — Python coding rules (uv, secrets, linting, file organization)
- **[Testing.md](Testing.md)** — Test patterns, mocking HTTP, integration tests

The agent-facing guides [`CLAUDE.md`](../CLAUDE.md) and [`AGENTS.md`](../AGENTS.md) are **generated** from [`AGENTS.src.md`](AGENTS.src.md). Edit the source and run `make agent-docs`; never edit the generated files directly.

# Contributing

This guide covers how to contribute to Mailbox and submit a PR.

## Getting Started

- Configure your environment via [README.md](README.md)
- Understand the conventions in [docs/README.md](docs/README.md) — especially [docs/KitAPI.md](docs/KitAPI.md)

## Workflow

- **Create a branch** (e.g. `feat/subscriber-import`, `fix/rate-limit-backoff`, `docs/kit-api-guide`)
- **Make your changes & tests**

```bash
make quality     # Format, lint, check Python types
make test        # Run the fast test suite
```

- **Commit changes** ([Conventional Commits](https://www.conventionalcommits.org/); pre-commit hooks run formatting, linting, and security checks)
- **Push your branch**
- **Open a Pull Request** against `main`
- **Wait for CI** (GitHub Actions runs formatting, linting, type checking, and tests)
- **Merge when green**

## Before you send mail

Any change that sends mail or mutates subscribers/tags in Kit must:

- Support a **dry-run** and be exercised with one
- Be **idempotent** or guarded against double-send/double-tag
- Be tested against a **dedicated test segment** — never a live audience

State how you verified this safely in the PR's test plan.

# Contributing to PACE Framework

Thank you for your interest in contributing. This document covers everything you need to get started.

---

## What belongs here

`pace-framework-starter` is the open-source framework template. Contributions should improve the framework itself — agents, orchestrator, platform adapters, config schema, reporter, docs — not any specific product built on top of it.

---

## Getting started

**Requirements:** Python 3.12+

```bash
git clone https://github.com/pace-framework-org/pace-framework-starter.git
cd pace-framework-starter
python -m venv .venv && source .venv/bin/activate
pip install -r pace/requirements.txt
```

Copy `pace/pace.config.yaml` and fill in your project details before running.

---

## Branch and PR conventions

- Branch from `main`: `fix/short-description` or `feat/short-description`
- One logical change per PR — keep diffs small and reviewable
- All PRs require at least one approval before merge
- `main` is protected: **all commits must be signed**

---

## Commit signing (required)

`main` enforces verified signatures. The easiest approach is SSH signing — no GPG needed.

**1. Generate a signing key**

```bash
ssh-keygen -t ed25519 -C "you@example.com" -f ~/.ssh/github_signing -N ""
```

**2. Add it to GitHub as a Signing Key**

Go to **github.com → Settings → SSH and GPG keys → New SSH key**, set the type to **Signing Key**, and paste the contents of `~/.ssh/github_signing.pub`.

**3. Configure git**

```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/github_signing.pub
git config --global commit.gpgsign true
```

All commits will now be signed automatically.

---

## Code style

- Follow existing patterns in the file you're editing
- No new dependencies without discussion in an issue first
- New platform adapters go in `pace/platforms/`
- New agents go in `pace/agents/`
- Config additions require changes to all three of: `PaceConfig` dataclass, `load_config()`, and `pace.config.yaml`

---

## Running tests

```bash
pytest -v --tb=short
```

All PRs must pass CI before review.

---

## Reporting issues

Use [GitHub Issues](https://github.com/pace-framework-org/pace-framework-starter/issues). Include:
- PACE version (`framework_version` in `pace.config.yaml`)
- Python version
- Platform type (`platform.type`)
- LLM provider and model
- Relevant error output or agent report

Label your issue `bug`, `enhancement`, or `question`.

---

## Good first issues

Look for issues tagged [`good first issue`](https://github.com/pace-framework-org/pace-framework-starter/issues?q=label%3A%22good+first+issue%22) — these are well-scoped and documented.

---

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE).

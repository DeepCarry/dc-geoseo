<p align="center">
  <img src="assets/banner.svg" alt="GEO-SEO Claude/Codex Toolkit" width="900"/>
</p>

<p align="center">
  <strong>GEO-first, SEO-supported.</strong> Dual-stack toolkit for Codex and Claude.
</p>

---

## What Changed (v2.0.0)

This repository now supports **two entry modes**:

1. **Codex CLI mode (recommended)** via unified `geo` command.
2. **Claude Skill mode (legacy-compatible)** via `geo/SKILL.md`, `skills/*`, and `agents/*`.

Codex authentication uses the **official OpenAI flow**:

- `codex login`
- no custom OAuth backend
- no local token storage by this project

---

## Quick Start

### Codex Mode (Recommended)

```bash
git clone https://github.com/DeepCarry/geo-seo-claude.git
cd geo-seo-claude
./install.sh          # defaults to --codex
# or: ./install-codex.sh
```

Then run:

```bash
geo doctor
geo quick https://example.com
geo audit https://example.com
```

### Claude Mode (Legacy)

```bash
./install.sh --claude
# or: ./install-claude.sh
```

---

## Unified CLI Commands

```bash
geo auth
geo doctor
geo audit <url>
geo quick <url>
geo citability <url>
geo crawlers <url>
geo llmstxt <url> --mode analyze|generate
geo brands <brand_name> [--domain domain.com]
geo platforms <url>
geo schema <url>
geo technical <url>
geo content <url>
geo report <url>
geo report-pdf <audit-json-path-or-url>
geo prospect <subcommand>
geo proposal <prospect-id-or-domain>
geo compare <baseline-audit.json> <current-audit.json>
```

Most commands support `--json` for machine-readable output.

---

## Packaging

This repo now includes `pyproject.toml` and installs as a Python package.

```bash
pip install -e .
# or
pipx install .
```

Entry point:

- `geo` -> `geo.cli:main`

---

## Architecture

- `src/geo/` — new reusable package and unified CLI.
- `scripts/` — legacy script engine kept for compatibility.
- `geo/`, `skills/`, `agents/` — Claude skill ecosystem kept intact.
- `schema/` — JSON-LD templates.
- `examples/` — sample audit/proposal/prospect artifacts.

---

## Codex Auth Notes

`geo auth` / `geo doctor` checks:

- whether `codex` is available in PATH
- whether login appears active (heuristic status checks)
- next step when missing login: `codex login`

---

## Legacy Compatibility

Existing Claude skill assets are preserved:

- `geo/SKILL.md`
- `skills/*/SKILL.md`
- `agents/*.md`

Use Claude path if your workflow depends on slash commands and Claude agent orchestration.

---

## License

MIT License

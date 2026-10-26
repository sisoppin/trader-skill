# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A Claude Code plugin: 11 `trader-*/` skill folders, each a `SKILL.md` plus a stdlib-only Python CLI. Skills share data through a `trader/` folder in the user's current working directory.

## Commands

- All tests (offline, under 1s): `python3 -m unittest discover -s tests -v`
- One file: `python3 -m unittest discover -s tests -p test_risk.py -v`
- One test: `cd tests && python3 -m unittest test_repo.Repo.test_root_matches_the_reel`
- Lint: `ruff check --select F,E9 --target-version py38 --no-cache .` (bugs only; the code uses `%` formatting on purpose, so don't apply ruff's default/UP rules). Don't add a pyproject.toml/ruff.toml, and keep `--no-cache`: the root allowlist test forbids new root entries.
- Tests load scripts by path through `tests/_load.py` `load(folder, name)` because folder names have hyphens. Put fixtures in `tests/fixtures/<skill>/` and send outputs to a `tempfile.TemporaryDirectory`. Never hit the network in tests.
- Don't run the tools from the repo root. They create `trader/` there, which fails `test_root_matches_the_reel`.

## Invariants enforced by `tests/test_repo.py`

- **No em dashes (U+2014)** in any .md/.py/.json/.csv/.txt/.xml file or LICENSE. That includes `.claude/` and this file. Use a colon, comma or parentheses.
- The repo root may contain only the entries listed in `test_root_matches_the_reel`. If you add a root file or folder, update that list.
- The skill count is hardcoded in several places. The `SKILLS` list, the `ABOUT` string ("11 Claude skills..."), `.claude-plugin/plugin.json` `description` (must equal `ABOUT`), the README first paragraph and "## The eleven" heading, and the README command table all have to agree. Use `/new-trader-skill` when adding a skill.
- SKILL.md frontmatter needs `name: <folder>` and a long `description:` (the frontmatter must be more than 200 chars). The body must be more than 60 lines. Order-path skills (`ORDER_PATH`) must say "not financial advice" and "yes".
- `trader-budget/config.example.json` must keep `"paper": true` and options off.
- Order amounts are strings (Alpaca `notional` format).

## Code rules

- Python 3.8+, standard library only. No pip dependencies and no manifest files. `pdftotext` is an optional external binary.
- SKILL.md files call their tool as `python3 "${CLAUDE_SKILL_DIR}/<script>.py"`. Docs are plain-language prose.
- SEC calls need a `SEC_USER_AGENT` ("Name email"), from the env or `sec_user_agent` in `trader/config.json`. Ask the user for it and never invent one. Respect the existing `time.sleep` rate limits (SEC allows at most 10 requests per second).

## Order safety (do not weaken)

Nothing in this repo places orders. An order reaches a broker only after all three gates:
1. `trader-risk/check.py` passes that exact order (fingerprint in `trader/state/risk.json`; exit 1 if any are blocked).
2. The user types an explicit yes, recorded by `trader-broker/ticket.py approve --reply`.
3. The broker MCP tool's "Needs approval" card.

Paper trading is the default, and options, margin and shorts are off. Never bypass a gate, auto-approve or default to live trading, even when the user is just using the skills to trade. Broker keys belong only in the MCP server env, never in chat, code or `trader/`.

## Scope and fork notes

- The pack is being converted to India: see `docs/superpowers/specs/2026-10-26-indian-market-design.md` and the plans in `docs/superpowers/plans/`. trader-alerts is converted (NSE clock, Kite quotes, `kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`). The other skills are still US until their phase lands. Shared helpers are copied into each skill that needs them and must stay byte-identical (`test_shared_helpers_are_identical`).
- This is a fork (`origin` = `sisoppin/trader-skill`). README, `plugin.json` and `test_repo.py` still hardcode `Jakeschincariol/trader-skill`, and a rebrand to sisoppin is planned. When rebranding, change README, `plugin.json`/`marketplace.json` and the `test_readme_carries_the_reel_copy` strings together.

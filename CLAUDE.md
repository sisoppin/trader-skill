# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A Claude Code plugin: 11 `trader-*/` skill folders, each a `SKILL.md` plus a stdlib-only Python CLI. Skills share data through a `trader/` folder in the user's current working directory.

## Commands

- All tests (offline, under 1s): `python3 -m unittest discover -s tests -v`
- One file: `python3 -m unittest discover -s tests -p test_risk.py -v`
- One test: `cd tests && python3 -m unittest test_repo.Repo.test_root_matches_the_reel`
- Lint: `ruff check --select F,E9 --target-version py38 --no-cache .` (bugs only; the code uses `%` formatting on purpose, so don't apply ruff's default/UP rules). Don't add a pyproject.toml/ruff.toml, and keep `--no-cache`: the root allowlist test forbids new root entries.
- Tests set `TRADER_TEST_CLOCK=1` through `tests/_load.py`; `--now` refuses to simulate time without it.
- Tests load scripts by path through `tests/_load.py` `load(folder, name)` because folder names have hyphens. Put fixtures in `tests/fixtures/<skill>/` and send outputs to a `tempfile.TemporaryDirectory`. Never hit the network in tests.
- Don't run the tools from the repo root. They create `trader/` there, which fails `test_root_matches_the_reel`.

## Invariants enforced by `tests/test_repo.py`

- **No em dashes (U+2014)** in any .md/.py/.json/.csv/.txt/.xml file or LICENSE. That includes `.claude/` and this file. Use a colon, comma or parentheses.
- The repo root may contain only the entries listed in `test_root_matches_the_reel`. If you add a root file or folder, update that list.
- The skill count is hardcoded in several places. The `SKILLS` list, the `ABOUT` string ("11 Claude skills..."), `.claude-plugin/plugin.json` `description` (must equal `ABOUT`), the README first paragraph and "## The eleven" heading, and the README command table all have to agree. Use `/new-trader-skill` when adding a skill.
- SKILL.md frontmatter needs `name: <folder>` and a long `description:` (the frontmatter must be more than 200 chars). The body must be more than 60 lines. Order-path skills (`ORDER_PATH`) must say "not financial advice" and "yes".
- `trader-budget/config.example.json` must keep `allow_mis`, `allow_short`, `allow_market_orders` and `allow_amo` false, `max_order_value` at Rs 10,000 or less, and no `"paper"` key (`test_live_defaults_are_cautious`).
- Order quantities and prices are strings, in Kite `place_order` field names.

## Code rules

- Python 3.8+, standard library only. No pip dependencies and no manifest files. `pdftotext` is an optional external binary.
- SKILL.md files call their tool as `python3 "${CLAUDE_SKILL_DIR}/<script>.py"`. Docs are plain-language prose.
- NSE calls go through `nse.Client` (cookie warm-up, a pause between requests, the daily cache in `trader/cache/nse/`). When NSE blocks a request, stop with exit code 2 and print the URL plus the `--file` or `--offline` rerun; never retry around a block.

## Order safety (do not weaken)

Nothing in this repo places orders. An order reaches a broker only after all three gates:
1. `trader-risk/check.py` passes that exact order (fingerprint in `trader/state/risk.json`; exit 1 if any are blocked).
2. The user types an explicit yes, recorded by `trader-broker/ticket.py approve --reply`.
3. The Kite connector's order tool set to "Needs approval", so its card asks once more.

Kite has no paper account: every order is LIVE, real money. `ticket.py` also refuses a risk check older than 10 minutes. The defaults are cautious (max order Rs 10,000, five orders a day, LIMIT only; MIS, MARKET, shorts and after-market orders off) and F&O, NRML and stop-loss orders are never supported. Never bypass a gate, auto-approve or loosen a limit for the user. Kite logins belong only in the connector, never in chat, code or `trader/`.

## Scope and fork notes

- The pack is being converted to India: see `docs/superpowers/specs/2026-10-26-indian-market-design.md` and the plans in `docs/superpowers/plans/`. Converted so far: trader-alerts (NSE clock, Kite quotes), the order path, trader-budget, trader-risk and trader-broker (Kite place_order shape, rupees, whole shares), the portfolio skills trader-rebalance and trader-tax (Kite holdings, Zerodha Console tradebook, Indian capital gains), trader-news and trader-insider (NSE announcements, SEBI insider trades, bulk and block deals; trader-pelosi was renamed trader-insider), and trader-analyst and trader-copycat (NSE results XBRL, NSE shareholding patterns, AMC portfolio sheets saved as CSV). The other skills are still US until their phase lands; their docs may still mention `ticket.py fill` or Alpaca. The shared helpers (`kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py`, `rupees.py`, `charges.py` whose source copy is in trader-budget, and `watchlist.py` whose source copy is in trader-news) are copied into each skill that needs them and must stay byte-identical (`test_shared_helpers_are_identical`).
- This is a fork of Jake Schincariol's US pack, now `sisoppin/trader-skill` (`origin`). The README install lines, `plugin.json` and `marketplace.json` (homepage, repository, author) and `test_repo.py` `REPO` all say `sisoppin/trader-skill`; change them together. LICENSE keeps the original copyright line above the new one.

---
name: new-trader-skill
description: Add a new trader-* skill to this plugin (folder, SKILL.md, stdlib CLI, tests, fixtures) and update every place that hardcodes the skill count or list so tests/test_repo.py still passes. Use when the user wants a new trader skill, e.g. an Indian market or Kite skill.
argument-hint: "<trader-name> <one-line purpose>"
disable-model-invocation: true
---

# Add a trader skill

Arguments: $ARGUMENTS (folder name, which must start with `trader-`, then its purpose).

Read two existing skills first as the template. Pick one close to the new one, for example `trader-alerts/` for a data tool or `trader-risk/` for an order-path tool. Read its test file in `tests/` too.

## 1. Folder and script

- Create `<name>/SKILL.md` and `<name>/<script>.py` at the repo root.
- Use Python 3.8+ and the standard library only. Give it an argparse CLI with `--help`. Read from and write to `trader/` relative to the cwd, as the other tools do.
- Network calls need a polite User-Agent and `time.sleep` pacing. SEC calls need `SEC_USER_AGENT`, and you must never invent one.
- Never place orders. If the skill proposes orders, it writes them for `trader-risk` to check, and amounts are strings.

## 2. SKILL.md

- Frontmatter: `name: <name>` (must equal the folder), a `description:` long enough that the frontmatter is more than 200 chars (list the trigger phrases), and `argument-hint:`.
- The body must be more than 60 lines. Call the tool as `python3 "${CLAUDE_SKILL_DIR}/<script>.py"`.
- If the skill can lead to an order, add it to `ORDER_PATH`. Its body must then include the phrase "not financial advice" and the explicit "yes" rule, so copy the safety block from an existing order-path skill.

## 3. Tests

- Add `tests/test_<short>.py` that uses `from _load import load, FIX` and `mod = load("<name>", "<script>")`.
- Put real-data fixtures in `tests/fixtures/<name>/`. Keep tests fully offline, with outputs in `tempfile.TemporaryDirectory`.

## 4. Update the hardcoded count and list (all must agree)

- `tests/test_repo.py`: add the folder to `SKILLS` (and `ORDER_PATH` if relevant). Update the number in `ABOUT`.
- `.claude-plugin/plugin.json`: `description` must equal the new `ABOUT` exactly.
- `README.md`: update the first paragraph (the `ABOUT` text) and the "## The eleven" heading, and add a `/<name>` row to the command table.
- Check `.claude-plugin/marketplace.json` for a matching description.
- Run `grep -rn "11 Claude skills\|eleven" .` to find leftovers.

## 5. Verify

- Run `python3 -m unittest discover -s tests -v`. Everything must pass.
- Check that no text file contains an em dash (U+2014).

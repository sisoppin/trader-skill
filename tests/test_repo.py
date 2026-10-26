import json
import os
import re
import unittest

from _load import ROOT

SKILLS = ["trader-copycat", "trader-news", "trader-budget", "trader-pelosi", "trader-analyst",
          "trader-screener", "trader-risk", "trader-broker", "trader-tax", "trader-alerts",
          "trader-rebalance"]
ABOUT = ("11 Claude skills that copy the investors you trust, watch the news and Congress, size every "
         "trade to your budget, and never place an order without your yes.")
# skills that can lead to an order carry the safety block
ORDER_PATH = ["trader-copycat", "trader-budget", "trader-pelosi", "trader-risk", "trader-broker",
              "trader-tax", "trader-alerts", "trader-rebalance"]
# helper modules copied into several skills; every copy must be the same bytes
SHARED = ["kite_snapshot.py", "nse.py", "nse_calendar.py", "nse_symbols.py", "rupees.py"]


def frontmatter(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return (m.group(1) if m else ""), text


def every_text_file():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".superpowers")]
        for f in files:
            if f.endswith((".md", ".py", ".json", ".csv", ".txt", ".xml")) or f == "LICENSE":
                yield os.path.join(base, f)


class Repo(unittest.TestCase):
    def test_eleven_skill_folders_at_the_root(self):
        found = sorted(d for d in os.listdir(ROOT)
                       if os.path.isfile(os.path.join(ROOT, d, "SKILL.md")))
        self.assertEqual(found, sorted(SKILLS))

    def test_root_matches_the_reel(self):
        root = sorted(d for d in os.listdir(ROOT) if not d.startswith((".git", ".superpowers")))  # .superpowers: git-ignored plan scratch
        self.assertEqual(root, sorted([".claude", ".claude-plugin", "CLAUDE.md", "LICENSE", "docs", "README.md",
                                       "tests"] + SKILLS))

    def test_frontmatter_name_and_description(self):
        for s in SKILLS:
            fm, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            self.assertIn("name: %s\n" % s, fm + "\n", s)
            self.assertRegex(fm, r"description: ", s)
            self.assertGreater(len(fm), 200, "%s description is too thin" % s)
            self.assertGreater(len(text.splitlines()), 60, s)

    def test_order_path_skills_carry_the_safety_rule(self):
        for s in ORDER_PATH:
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("not financial advice", low, s)
            self.assertIn("yes", low, s)

    def test_plugin_manifest_points_at_the_root_skills(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json")) as fh:
            plugin = json.load(fh)
        self.assertEqual(plugin["name"], "trader-skill")
        self.assertEqual(plugin["skills"], "./")
        self.assertEqual(plugin["description"], ABOUT)
        with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json")) as fh:
            market = json.load(fh)
        self.assertEqual(market["name"], "trader-skill")
        self.assertEqual(market["plugins"][0]["name"], "trader-skill")

    def test_readme_carries_the_reel_copy(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
            readme = " ".join(fh.read().split())
        self.assertTrue(readme.startswith("# The Trader skill"))
        for line in (ABOUT,
                     "https://github.com/Jakeschincariol/trader-skill install skill",
                     "/plugin marketplace add Jakeschincariol/trader-skill",
                     "/plugin install trader-skill@trader-skill",
                     "## Fine print"):
            self.assertIn(line, readme)
        for s in SKILLS:
            self.assertIn("/" + s, readme, s)

    def test_no_em_dashes_and_no_personal_email(self):
        for path in every_text_file():
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            rel = os.path.relpath(path, ROOT)
            self.assertNotIn("\u2014", text, rel)
            self.assertNotIn("jakeschincariol" + "@" + "gmail.com", text, rel)  # built, so this file passes too

    def test_live_defaults_are_cautious(self):
        with open(os.path.join(ROOT, "trader-budget", "config.example.json")) as fh:
            cfg = json.load(fh)
        for k in ("allow_mis", "allow_short", "allow_market_orders", "allow_amo"):
            self.assertIs(cfg[k], False, k)
        self.assertLessEqual(float(cfg["max_order_value"]), 10000)
        self.assertNotIn("paper", cfg)

    def test_shared_helpers_are_identical(self):
        for name in SHARED:
            copies = [os.path.join(ROOT, s, name) for s in SKILLS if os.path.isfile(os.path.join(ROOT, s, name))]
            self.assertTrue(copies, "%s exists in no skill" % name)
            texts = set()
            for p in copies:
                with open(p, "rb") as fh:
                    texts.add(fh.read())
            self.assertEqual(len(texts), 1, "copies of %s differ: %s" % (name, copies))

    def test_converted_order_path_skills_say_live(self):
        for s in ("trader-budget", "trader-risk", "trader-broker"):
            _, text = frontmatter(os.path.join(ROOT, s, "SKILL.md"))
            low = " ".join(text.lower().split())
            self.assertIn("live", low, s)
            self.assertIn("real money", low, s)
            self.assertNotIn("alpaca", low, s)
            self.assertNotIn("paper trading", low, s)

    def test_every_imported_helper_is_in_the_same_skill(self):
        names = {n[:-3] for n in SHARED}
        for s in SKILLS:
            folder = os.path.join(ROOT, s)
            for f in sorted(os.listdir(folder)):
                if not f.endswith(".py"):
                    continue
                with open(os.path.join(folder, f), encoding="utf-8") as fh:
                    used = set(re.findall(r"^(?:import|from) (\w+)", fh.read(), re.M))
                for mod in sorted(used & names):
                    self.assertTrue(os.path.isfile(os.path.join(folder, mod + ".py")),
                                    "%s/%s imports %s, which is not in %s" % (s, f, mod, s))

    def test_alerts_example_rules_are_nse(self):
        with open(os.path.join(ROOT, "trader-alerts", "alerts.example.json")) as fh:
            rules = json.load(fh)["rules"]
        syms = {r["symbol"] for r in rules if "symbol" in r}
        self.assertEqual(syms, {"INFY", "RELIANCE", "TCS", "HDFCBANK"})
        self.assertIn("mis_warning", {r["type"] for r in rules})


if __name__ == "__main__":
    unittest.main()

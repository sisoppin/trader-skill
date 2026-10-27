# India Phase 4b (Analyst and Copycat) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert trader-analyst to quarterly results filed with NSE, and trader-copycat to Indian investors (stakes above 1% in NSE shareholding patterns, over symbols the user lists) and mutual funds (the AMC's monthly portfolio sheet saved as CSV). Both write the files the rest of the pack reads: `trader/metrics.json` and `trader/targets.json`.

**Architecture:**
- **trader-analyst** (`results.py`) reads NSE's integrated-filing (financials) list per stock and the newest five quarterly XBRL files. Each file holds one quarter, so the tool gets YoY, QoQ and TTM by lining quarters up.
- **trader-copycat** has two parsers and a CLI. `shp.py` reads shareholding XBRL: names on `D_` contexts, shares on the matching instant contexts, and PAC repeats skipped. `amc.py` reads AMC CSVs: header found by column names, equity ISINs only. `copycat.py` scales either to weights and refuses to write from a partial read.
- All NSE access goes through the shared `nse.py`, with `--offline DIR` as the fallback when NSE blocks.

**Tech Stack:** Python 3.8+, standard library only (`xml.etree`, `csv`), `unittest` with offline fixtures:
- The NSE files are real, captured 2026-10-27. The XBRL files are trimmed to the facts the parsers read, and each says so in an XML comment.
- The two AMC sheets are synthetic and labelled as such.

**Spec:** `docs/superpowers/specs/2026-10-26-indian-market-design.md` (sections 2, 3.3, 9 phase 4). Task 3 updates two spec lines with what the probes found.

**Branch:** `feat/india-phase4b`, branched from `feat/india-phase4a`.

**Provenance:** every code block below was drafted and run in a scratch worktree first. The suite passed with 326 tests on Python 3.12 and 3.8, and ruff was clean. The expected values come from those runs on real NSE data.

**Probe findings that shaped the design (2026-10-27):**
- `corporates-financial-results` and `results-comparision` stop at the quarter ended Dec 2024: SEBI moved results to the integrated filing in 2025.
- `integrated-filing-results?...&type=Integrated%20Filing-%20Financials` lists every quarter since Mar 2025, each with an XBRL link. Each XBRL file holds one quarter, plus year-to-date.
- Banks file a different format: InterestEarned, ProfitLossForThePeriod, EPS AfterExtraordinaryItems.
- Shareholding XBRL: NCC repeats Rekha Jhunjhunwala's holding under `PAC_Public` contexts. Counting every named row would double her stake.

## Global Constraints

- Python 3.8 or newer, standard library only. No em dashes (U+2014) in any .md, .py, .json, .csv, .txt or .xml file.
- Shared helpers are copied unchanged from their source copy, and `tests/test_repo.py` checks that every copy is identical and that every imported helper is present:
  - `kite_snapshot.py`, `nse.py`, `nse_calendar.py`, `nse_symbols.py` and `rupees.py` come from `trader-alerts/`.
  - `watchlist.py` comes from `trader-news/`.
- NSE access only through `nse.Client`. A blocked request exits 2 and prints the URL plus the `--offline` rerun.
- Any partial read (an error, a block, a missing price) exits 2.
- Tests are fully offline. `--now` works only with `TRADER_TEST_CLOCK=1` (`tests/_load.py` sets it). Never run a tool from the repo root. Lint with `--no-cache`.
- Commit messages end with a Co-Authored-By trailer.
- Full check: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`

## Review Focus

1. **A missing comparison quarter** (late filing, basis change, history before Apr 2025): the growth or TTM figure is n/a and never estimated. Covered by `test_missing_quarter_leaves_qoq_and_ttm_empty` and `test_bank_with_one_quarter`.
2. **An investor named twice in one pattern** (two accounts, two categories, PAC repeats): accounts add up, and PAC repeats are not counted. Covered by `test_titan_two_accounts_add_up` and `test_persons_acting_in_concert_are_not_counted_twice`.
3. **A partial read turned into targets** (a failed stock, a missing price, an unlisted fund holding inside the top N): nothing is written, and the run exits 2. Covered by `test_partial_read_refuses_to_write`, `test_missing_price_refuses_to_write` and `test_unlisted_stock_inside_the_top_refuses_to_write`.
4. **Bonds and debentures of the same issuer as a held stock** (INE...08 ISINs): never counted as equity. Covered by `test_october_sheet` and `test_equity_isins`.
5. **A block page instead of XBRL**: an error line, and the cached copy is forgotten. Covered by `test_symbol_is_encoded_and_a_bad_xbrl_is_forgotten` and `test_symbol_is_encoded_and_a_block_page_is_forgotten`.

---

### Task 1: trader-analyst on NSE quarterly results

**Files:**
- Delete: `trader-analyst/facts.py`, `tests/fixtures/trader-analyst/` (the SEC fixtures)
- Copy (unchanged): `trader-alerts/{kite_snapshot,nse,nse_calendar,nse_symbols,rupees}.py` and `trader-news/watchlist.py` into `trader-analyst/`
- Create: `trader-analyst/results.py`, plus the 8 fixture files in `tests/fixtures/trader-analyst/`
- Replace: `tests/test_analyst.py`, `trader-analyst/SKILL.md`, `trader-analyst/metrics.example.json`
- Modify: `README.md` (analyst lines)

**Interfaces:**
- Consumes: `nse.Client.get_json/get_text/forget`, `nse.read_file`, `nse.read_json_file`, `watchlist.watch_list`, `rupees.inr`, and `screen.load_metrics` (trader-screener, test only)
- Produces:
  - `results.parse_list(doc, symbol) -> [{quarter, basis, xbrl, filed, broadcast, name}]`
  - `results.pick(filings, standalone=False)`
  - `results.parse_xbrl(text) -> {period_end, FIELD: float}`
  - `results.figures(facts)`
  - `results.metrics(...)`
  - `results.fetch(symbol, client=None, offline=None, standalone=False) -> row`
  - The `trader/metrics.json` shape: `{as_of, complete, errors, blocked, companies: [row]}`. A row carries `symbol, name, basis, period_end, quarter, filed, bank, revenue, net_profit, eps, operating_margin, net_margin, revenue_growth_yoy, revenue_growth_qoq, net_profit_growth_yoy, net_profit_growth_qoq, eps_growth_yoy, revenue_ttm, net_profit_ttm, eps_ttm, source`.

- [ ] **Step 1: Remove the SEC version and write the fixtures**

```bash
git rm -q trader-analyst/facts.py
git rm -q -r tests/fixtures/trader-analyst
```

The JSON lists are real NSE answers, trimmed to the quarters used. The XBRL files are real, trimmed to the parsed facts, and labelled in their first comment.

`tests/fixtures/trader-analyst/INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_Banking/2026-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_Banking/2026-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500180</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">HDFCBANK</in-capmkt:Symbol>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2026-09-30</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Standalone</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:InterestEarned contextRef="OneD" decimals="-6" unitRef="INR">834266000000</in-capmkt:InterestEarned>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-5" unitRef="INR">138310200000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-5" unitRef="INR">972576200000</in-capmkt:Income>
<in-capmkt:OperatingProfitBeforeProvisionAndContingencies contextRef="OneD" decimals="-5" unitRef="INR">294834200000</in-capmkt:OperatingProfitBeforeProvisionAndContingencies>
<in-capmkt:ProfitLossFromOrdinaryActivitiesBeforeTax contextRef="OneD" decimals="-6" unitRef="INR">259098000000</in-capmkt:ProfitLossFromOrdinaryActivitiesBeforeTax>
<in-capmkt:ProfitLossForThePeriod contextRef="OneD" decimals="-5" unitRef="INR">195099600000</in-capmkt:ProfitLossForThePeriod>
<in-capmkt:BasicEarningsPerShareAfterExtraordinaryItems contextRef="OneD" decimals="INF" unitRef="INRPerShare">12.66</in-capmkt:BasicEarningsPerShareAfterExtraordinaryItems>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/INTEGRATED_FILING_INDAS_1551001_16102025094433_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1551001_16102025094433_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2025-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2025-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2025-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2025-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500209</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">INFY</in-capmkt:Symbol>
<in-capmkt:NameOfTheCompany contextRef="OneD">INFOSYS LIMITED</in-capmkt:NameOfTheCompany>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2025-09-30</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" decimals="-7" unitRef="INR">444900000000</in-capmkt:RevenueFromOperations>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-7" unitRef="INR">9820000000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-7" unitRef="INR">454720000000</in-capmkt:Income>
<in-capmkt:FinanceCosts contextRef="OneD" decimals="-7" unitRef="INR">1060000000</in-capmkt:FinanceCosts>
<in-capmkt:ProfitBeforeTax contextRef="OneD" decimals="-7" unitRef="INR">102290000000</in-capmkt:ProfitBeforeTax>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" decimals="-7" unitRef="INR">73750000000</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" decimals="-7" unitRef="INR">73640000000</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD" decimals="INF" unitRef="INRPerShare">17.76</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/INTEGRATED_FILING_INDAS_1601190_14012026083832_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1601190_14012026083832_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2025-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2025-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2025-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2025-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500209</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-10-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">INFY</in-capmkt:Symbol>
<in-capmkt:NameOfTheCompany contextRef="OneD">INFOSYS LIMITED</in-capmkt:NameOfTheCompany>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2025-12-31</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" decimals="-7" unitRef="INR">454790000000</in-capmkt:RevenueFromOperations>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-7" unitRef="INR">11390000000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-7" unitRef="INR">466180000000</in-capmkt:Income>
<in-capmkt:FinanceCosts contextRef="OneD" decimals="-7" unitRef="INR">1000000000</in-capmkt:FinanceCosts>
<in-capmkt:ProfitBeforeTax contextRef="OneD" decimals="-7" unitRef="INR">92290000000</in-capmkt:ProfitBeforeTax>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" decimals="-7" unitRef="INR">66660000000</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" decimals="-7" unitRef="INR">66540000000</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD" decimals="INF" unitRef="INRPerShare">16.17</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/INTEGRATED_FILING_INDAS_1658040_23042026090154_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1658040_23042026090154_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500209</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">INFY</in-capmkt:Symbol>
<in-capmkt:NameOfTheCompany contextRef="OneD">INFOSYS LIMITED</in-capmkt:NameOfTheCompany>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2026-03-31</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" decimals="-7" unitRef="INR">464020000000</in-capmkt:RevenueFromOperations>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-7" unitRef="INR">11590000000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-7" unitRef="INR">475610000000</in-capmkt:Income>
<in-capmkt:FinanceCosts contextRef="OneD" decimals="-7" unitRef="INR">1050000000</in-capmkt:FinanceCosts>
<in-capmkt:ProfitBeforeTax contextRef="OneD" decimals="-7" unitRef="INR">107970000000</in-capmkt:ProfitBeforeTax>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" decimals="-7" unitRef="INR">85090000000</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" decimals="-7" unitRef="INR">85010000000</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD" decimals="INF" unitRef="INRPerShare">21.01</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/INTEGRATED_FILING_INDAS_1700136_23072026054446_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1700136_23072026054446_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500209</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">INFY</in-capmkt:Symbol>
<in-capmkt:NameOfTheCompany contextRef="OneD">INFOSYS LIMITED</in-capmkt:NameOfTheCompany>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2026-06-30</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" decimals="-7" unitRef="INR">482110000000</in-capmkt:RevenueFromOperations>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-7" unitRef="INR">9840000000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-7" unitRef="INR">491950000000</in-capmkt:Income>
<in-capmkt:FinanceCosts contextRef="OneD" decimals="-7" unitRef="INR">1190000000</in-capmkt:FinanceCosts>
<in-capmkt:ProfitBeforeTax contextRef="OneD" decimals="-7" unitRef="INR">110280000000</in-capmkt:ProfitBeforeTax>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" decimals="-7" unitRef="INR">77750000000</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" decimals="-7" unitRef="INR">77690000000</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD" decimals="INF" unitRef="INRPerShare">19.19</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/INTEGRATED_FILING_INDAS_1745058_23102026082117_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1745058_23102026082117_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-capmkt="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt" xmlns:in-capmkt-ent="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt/in-capmkt-ent" xmlns:in-capmkt-roles="http://www.sebi.gov.in/xbrl/IntegratedFinance_IndAS/2026-01-31/in-capmkt-roles" xmlns:in-capmkt-types="http://www.sebi.gov.in/xbrl/2026-01-31/in-capmkt-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink">
<xbrli:context id="OneD"><xbrli:entity><xbrli:identifier scheme="http://www.sebi.gov.in/in-capmkt/ScripCode">500209</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:unit id="INR"><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unit>
<xbrli:unit id="INRPerShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:INR</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
<in-capmkt:Symbol contextRef="OneD">INFY</in-capmkt:Symbol>
<in-capmkt:NameOfTheCompany contextRef="OneD">INFOSYS LIMITED</in-capmkt:NameOfTheCompany>
<in-capmkt:LevelOfRounding contextRef="OneD">Crores</in-capmkt:LevelOfRounding>
<in-capmkt:DateOfEndOfReportingPeriod contextRef="OneD">2026-09-30</in-capmkt:DateOfEndOfReportingPeriod>
<in-capmkt:NatureOfReportStandaloneConsolidated contextRef="OneD">Consolidated</in-capmkt:NatureOfReportStandaloneConsolidated>
<in-capmkt:RevenueFromOperations contextRef="OneD" decimals="-7" unitRef="INR">492440000000</in-capmkt:RevenueFromOperations>
<in-capmkt:OtherIncome contextRef="OneD" decimals="-7" unitRef="INR">8480000000</in-capmkt:OtherIncome>
<in-capmkt:Income contextRef="OneD" decimals="-7" unitRef="INR">500920000000</in-capmkt:Income>
<in-capmkt:FinanceCosts contextRef="OneD" decimals="-7" unitRef="INR">1150000000</in-capmkt:FinanceCosts>
<in-capmkt:ProfitBeforeTax contextRef="OneD" decimals="-7" unitRef="INR">110630000000</in-capmkt:ProfitBeforeTax>
<in-capmkt:ProfitLossForPeriod contextRef="OneD" decimals="-7" unitRef="INR">78380000000</in-capmkt:ProfitLossForPeriod>
<in-capmkt:ProfitOrLossAttributableToOwnersOfParent contextRef="OneD" decimals="-7" unitRef="INR">78230000000</in-capmkt:ProfitOrLossAttributableToOwnersOfParent>
<in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations contextRef="OneD" decimals="INF" unitRef="INRPerShare">19.32</in-capmkt:BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations>
</xbrli:xbrl>
```

`tests/fixtures/trader-analyst/results-HDFCBANK.json`:

```json
{
 "data": [
  {
   "attFileSize": "0 Bytes",
   "audited": "Un-Audited",
   "broadcast_Date": "17-Oct-2026 17:47:13",
   "cmName": "HDFC Bank Limited",
   "consolidated": "Consolidated",
   "creation_Date": "17-Oct-2026 17:48:12",
   "diff": "00:00:59",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_BANKING_202132_17102026174812_iXBRL_WEB.html",
   "ixbrlFileSize": "62.00 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-SEP-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "202132",
   "smName": "HDFC Bank Limited",
   "symbol": "HDFCBANK",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_BANKING_1740913_17102026054812_WEB.xml",
   "xbrlFileSize": "78.86 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Un-Audited",
   "broadcast_Date": "17-Oct-2026 17:46:30",
   "cmName": "HDFC Bank Limited",
   "consolidated": "Standalone",
   "creation_Date": "17-Oct-2026 17:48:07",
   "diff": "00:01:37",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_BANKING_202131_17102026174807_iXBRL_WEB.html",
   "ixbrlFileSize": "528.46 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-SEP-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "202131",
   "smName": "HDFC Bank Limited",
   "symbol": "HDFCBANK",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml",
   "xbrlFileSize": "1.30 MB"
  }
 ],
 "size": 2,
 "page": 1,
 "totalCount": 2
}
```

`tests/fixtures/trader-analyst/results-INFY.json`:

```json
{
 "data": [
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Oct-2026 20:19:37",
   "cmName": "Infosys Limited",
   "consolidated": "Standalone",
   "creation_Date": "23-Oct-2026 20:21:12",
   "diff": "00:01:35",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_203728_23102026202112_iXBRL_WEB.html",
   "ixbrlFileSize": "739.75 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-SEP-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "203728",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1745057_23102026082111_WEB.xml",
   "xbrlFileSize": "1.86 MB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Oct-2026 20:16:14",
   "cmName": "Infosys Limited",
   "consolidated": "Consolidated",
   "creation_Date": "23-Oct-2026 20:21:18",
   "diff": "00:05:04",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_203729_23102026202117_iXBRL_WEB.html",
   "ixbrlFileSize": "96.60 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-SEP-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "203729",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1745058_23102026082117_WEB.xml",
   "xbrlFileSize": "148.74 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Jul-2026 17:41:05",
   "cmName": "Infosys Limited",
   "consolidated": "Standalone",
   "creation_Date": "23-Jul-2026 17:41:19",
   "diff": "00:00:14",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_177355_23072026174118_iXBRL_WEB.html",
   "ixbrlFileSize": "41.99 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-JUN-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "177355",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1700098_23072026054118_WEB.xml",
   "xbrlFileSize": "21.70 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Jul-2026 17:40:57",
   "cmName": "Infosys Limited",
   "consolidated": "Consolidated",
   "creation_Date": "23-Jul-2026 17:44:46",
   "diff": "00:03:49",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_177385_23072026174446_iXBRL_WEB.html",
   "ixbrlFileSize": "45.67 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "30-JUN-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "177385",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1700136_23072026054446_WEB.xml",
   "xbrlFileSize": "52.38 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Apr-2026 20:47:44",
   "cmName": "Infosys Limited",
   "consolidated": "Standalone",
   "creation_Date": "23-Apr-2026 21:02:05",
   "diff": "00:14:21",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_152466_23042026210204_iXBRL_WEB.html",
   "ixbrlFileSize": "703.76 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "31-MAR-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "152466",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1658041_23042026090203_WEB.xml",
   "xbrlFileSize": "1.74 MB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "23-Apr-2026 20:47:17",
   "cmName": "Infosys Limited",
   "consolidated": "Consolidated",
   "creation_Date": "23-Apr-2026 21:01:54",
   "diff": "00:14:37",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_152465_23042026210154_iXBRL_WEB.html",
   "ixbrlFileSize": "96.57 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "31-MAR-2026",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "152465",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1658040_23042026090154_WEB.xml",
   "xbrlFileSize": "147.70 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "14-Jan-2026 20:38:27",
   "cmName": "Infosys Limited",
   "consolidated": "Consolidated",
   "creation_Date": "14-Jan-2026 20:38:32",
   "diff": "00:00:05",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_135037_14012026203832_iXBRL_WEB.html",
   "ixbrlFileSize": "48.84 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "31-DEC-2025",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "135037",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1601190_14012026083832_WEB.xml",
   "xbrlFileSize": "81.46 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "14-Jan-2026 20:38:22",
   "cmName": "Infosys Limited",
   "consolidated": "Standalone",
   "creation_Date": "14-Jan-2026 20:38:25",
   "diff": "00:00:03",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_135036_14012026203824_iXBRL_WEB.html",
   "ixbrlFileSize": "63.13 KB",
   "pdf_attach": "https://nsearchives.nseindia.com/corporate/null",
   "qe_Date": "31-DEC-2025",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "135036",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1601189_14012026083824_WEB.xml",
   "xbrlFileSize": "53.89 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "16-Oct-2025 21:44:34",
   "cmName": "Infosys Limited",
   "consolidated": "Consolidated",
   "creation_Date": "16-Oct-2025 21:44:34",
   "diff": "00:00:00",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_120286_16102025214434_iXBRL_WEB.html",
   "ixbrlFileSize": "82.73 KB",
   "pdf_attach": null,
   "qe_Date": "30-SEP-2025",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "120286",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1551001_16102025094433_WEB.xml",
   "xbrlFileSize": "104.69 KB"
  },
  {
   "attFileSize": "0 Bytes",
   "audited": "Audited",
   "broadcast_Date": "16-Oct-2025 21:39:13",
   "cmName": "Infosys Limited",
   "consolidated": "Standalone",
   "creation_Date": "16-Oct-2025 21:39:15",
   "diff": "00:00:02",
   "ixbrl": "https://nsearchives.nseindia.com/corporate/ixbrl/INTEGRATED_FILING_INDAS_120285_16102025213914_iXBRL_WEB.html",
   "ixbrlFileSize": "676.85 KB",
   "pdf_attach": null,
   "qe_Date": "30-SEP-2025",
   "revised_Date": null,
   "revision_Remark": null,
   "seq_Id": "120285",
   "smName": "Infosys Limited",
   "symbol": "INFY",
   "type": "Integrated Filing- Financials",
   "type_Sub": "Original",
   "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/INTEGRATED_FILING_INDAS_1550998_16102025093913_WEB.xml",
   "xbrlFileSize": "1.74 MB"
  }
 ],
 "size": 10,
 "page": 1,
 "totalCount": 10
}
```


- [ ] **Step 2: Write the failing tests**

Replace `tests/test_analyst.py` with:

```python
import datetime
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

res = load("trader-analyst", "results")
screen = load("trader-screener", "screen")

ADIR = os.path.join(FIX, "trader-analyst")
NOW = "2026-10-27T10:00"
INFY_Q2 = "INTEGRATED_FILING_INDAS_1745058_23102026082117_WEB.xml"
BANK = "INTEGRATED_FILING_BANKING_1740912_17102026054806_WEB.xml"


def read(name):
    with open(os.path.join(ADIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = res.main(argv)
    return code, out.getvalue(), err.getvalue()


class Xbrl(unittest.TestCase):
    def test_infy_quarter(self):
        f = res.parse_xbrl(read(INFY_Q2))
        self.assertEqual(f["period_end"], datetime.date(2026, 9, 30))
        q = res.figures(f)
        self.assertEqual((q["revenue"], q["net_profit"], q["eps"], q["bank"]), (492440000000.0, 78230000000.0, 19.32, False))
        self.assertEqual(q["operating_profit"], 110630000000.0 + 1150000000.0 - 8480000000.0)

    def test_bank_format(self):
        q = res.figures(res.parse_xbrl(read(BANK)))
        self.assertEqual((q["revenue"], q["net_profit"], q["eps"], q["bank"], q["operating_profit"]),
                         (834266000000.0, 195099600000.0, 12.66, True, None))

    def test_block_page_is_an_error(self):
        with self.assertRaises(res.ResultsError):
            res.parse_xbrl("<html><body>Access Denied</body></html>")


class Labels(unittest.TestCase):
    def test_fiscal_quarters(self):
        self.assertEqual([res.fy_label(datetime.date(*d)) for d in ((2026, 9, 30), (2026, 3, 31), (2025, 12, 31))],
                         ["Q2 FY27", "Q4 FY26", "Q3 FY26"])

    def test_quarter_steps(self):
        self.assertEqual(res._months_back(datetime.date(2026, 3, 31), 3), datetime.date(2025, 12, 31))
        self.assertEqual(res._months_back(datetime.date(2026, 9, 30), 12), datetime.date(2025, 9, 30))
        self.assertEqual(res._months_back(datetime.date(2026, 6, 30), 3), datetime.date(2026, 3, 31))


class Pick(unittest.TestCase):
    def f(self, q, basis, filed, link="x.xml"):
        return {"quarter": datetime.date(*q), "basis": basis, "xbrl": link, "filed": datetime.date(*filed),
                "broadcast": "", "name": "X"}

    def test_revised_filing_replaces_the_original_and_consolidated_wins(self):
        got = res.pick([self.f((2026, 9, 30), "consolidated", (2026, 10, 20), "a.xml"),
                        self.f((2026, 9, 30), "consolidated", (2026, 10, 25), "b.xml"),
                        self.f((2026, 9, 30), "standalone", (2026, 10, 26), "c.xml")])
        self.assertEqual([g["xbrl"] for g in got], ["b.xml"])

    def test_standalone_only_company(self):
        got = res.pick([self.f((2026, 9, 30), "standalone", (2026, 10, 20))])
        self.assertEqual(got[0]["basis"], "standalone")

    def test_not_a_list(self):
        with self.assertRaises(res.ResultsError):
            res.parse_list([], "INFY")


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_infy_metrics(self):
        code, text, _ = run(["--symbols", "INFY", "--offline", ADIR, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["quarter"], r["basis"], r["filed"]), ("Q2 FY27", "consolidated", "2026-10-23"))
        self.assertEqual((r["revenue_growth_yoy"], r["revenue_growth_qoq"], r["net_profit_growth_yoy"],
                          r["net_profit_growth_qoq"], r["eps_growth_yoy"]), (10.7, 2.1, 6.2, 0.7, 8.8))
        self.assertEqual((r["operating_margin"], r["net_margin"], r["eps_ttm"]), (21.0, 15.9, 75.69))

    def test_text_report(self):
        code, text, _ = run(["--symbols", "INFY", "--offline", ADIR, "--now", NOW])
        self.assertIn("INFY  Q2 FY27 (2026-09-30, consolidated)", text)
        self.assertIn("revenue     Rs 49,244 cr  (+10.7% YoY, +2.1% QoQ)", text)
        self.assertIn("Not financial advice", text)

    def test_bank_with_one_quarter(self):
        code, text, _ = run(["--symbols", "HDFCBANK", "--standalone", "--offline", ADIR, "--now", NOW, "--json"])
        self.assertEqual(code, 0)
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["bank"], r["operating_margin"], r["revenue_growth_yoy"], r["eps_ttm"]), (True, None, None, None))

    def test_missing_quarter_leaves_qoq_and_ttm_empty(self):
        d = os.path.join(self.tmp.name, "gap")
        shutil.copytree(ADIR, d)
        with open(os.path.join(d, "results-INFY.json")) as fh:
            doc = json.load(fh)
        doc["data"] = [r for r in doc["data"] if r["qe_Date"] != "30-JUN-2026"]
        with open(os.path.join(d, "results-INFY.json"), "w") as fh:
            json.dump(doc, fh)
        code, text, _ = run(["--symbols", "INFY", "--offline", d, "--now", NOW, "--json"])
        r = json.loads(text)["companies"][0]
        self.assertEqual((r["revenue_growth_qoq"], r["eps_ttm"], r["revenue_growth_yoy"]), (None, None, 10.7))

    def test_write_marks_partial_runs_and_the_screener_reads_it(self):
        out = os.path.join(self.tmp.name, "metrics.json")
        code, text, _ = run(["--symbols", "INFY", "TCS", "--offline", ADIR, "--now", NOW, "--write", out])
        self.assertEqual(code, 2)
        self.assertIn("error: TCS: cannot read", text)
        with open(out) as fh:
            doc = json.load(fh)
        self.assertEqual((doc["complete"], len(doc["companies"]), len(doc["errors"])), (False, 1, 1))
        self.assertEqual([c["symbol"] for c in screen.load_metrics(out)], ["INFY"])

    def test_no_symbols(self):
        code, _, err = run(["--kite-dir", self.tmp.name, "--targets", os.path.join(self.tmp.name, "none.json"),
                            "--offline", ADIR, "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("which stocks?", err)


class Network(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "real"):
            res.nse.Client = self.real

    def test_symbol_is_encoded_and_a_bad_xbrl_is_forgotten(self):
        doc = json.loads(read("results-INFY.json"))

        class Client:
            urls, forgot = [], []

            def get_json(self, url, cache=True):
                self.urls.append(url)
                return doc

            def get_text(self, url, cookie=True, cache=True):
                return "<html>blocked</html>"

            def forget(self, url):
                self.forgot.append(url)
        c = Client()
        with self.assertRaises(res.ResultsError):
            res.fetch("M&M", c)
        self.assertTrue(c.urls[0].endswith("symbol=M%26M&type=Integrated%20Filing-%20Financials"))
        self.assertEqual(len(c.forgot), 1)

    def test_blocked_exits_2_with_the_offline_hint(self):
        class Client:
            def get_json(self, url, cache=True):
                raise res.nse.NseBlocked(url, "HTTP 403")
        self.real = res.nse.Client
        res.nse.Client = Client
        code, text, _ = run(["--symbols", "INFY", "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("blocked: ", text)
        self.assertIn("--offline", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_analyst.py -v`
Expected: an ERROR, because `trader-analyst/results.py` does not exist.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/kite_snapshot.py trader-alerts/nse.py trader-alerts/nse_calendar.py trader-alerts/nse_symbols.py trader-alerts/rupees.py trader-analyst/
cp trader-news/watchlist.py trader-analyst/
```

`trader-analyst/results.py`:

```python
#!/usr/bin/env python3
"""Quarterly results for trader-analyst, from the financials companies file with NSE.

    python3 results.py                                  # your Kite holdings and trader/targets.json
    python3 results.py --symbols INFY TCS HDFCBANK
    python3 results.py --symbols INFY --standalone      # the parent company alone, not the group
    python3 results.py --symbols INFY --write           # also save trader/metrics.json for the screener
    python3 results.py --symbols INFY --offline DIR     # NSE blocked you: files saved from a browser

Source: NSE's integrated filing (financials) list for each stock,
  https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=<SYMBOL>&type=Integrated%20Filing-%20Financials
and the XBRL file each row links to (https://nsearchives.nseindia.com/corporate/xbrl/...). Each XBRL file holds
one quarter, so the tool reads the newest five: this quarter, the one before (QoQ), the same quarter a year
earlier (YoY), and four in a row for the trailing twelve months (TTM). Filings from before April 2025 used
NSE's older results page and are not read.

Numbers are in rupees as filed. Revenue is revenue from operations (interest earned for a bank). Net profit
is the profit attributable to the owners of the company when the filing gives it. Operating margin is
(profit before tax + finance costs - other income) / revenue; it is left empty for banks, whose format has no
such line. A company that files only standalone results is read standalone, and the row says so.

Exit code 0 when every stock was read, 2 when any stock could not be read or NSE blocked a request (the
message names the URL to open and how to rerun with --offline).

These are the company's reported numbers, not a forecast. Not financial advice.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.parse
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import kite_snapshot
import nse
import nse_calendar
import nse_symbols
import watchlist
from rupees import inr

LIST_URL = ("https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=%s"
            "&type=Integrated%%20Filing-%%20Financials")
QUARTERS = 5
FIELDS = ("RevenueFromOperations", "InterestEarned", "OtherIncome", "FinanceCosts", "ProfitBeforeTax",
          "ProfitOrLossAttributableToOwnersOfParent", "ProfitLossForPeriod", "ProfitLossForThePeriod",
          "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
          "BasicEarningsPerShareAfterExtraordinaryItems")


class ResultsError(Exception):
    pass


def _date(text, fmt):
    try:
        return datetime.datetime.strptime(str(text).strip(), fmt).date()
    except ValueError:
        return None


def parse_list(doc, symbol):
    """NSE's integrated-filing list ({"data": [...]}) -> filings {quarter, basis, xbrl, filed, name}."""
    rows = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ResultsError("the results list for %s is not NSE's answer (no data list)" % symbol)
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        q = _date(r.get("qe_Date"), "%d-%b-%Y")
        filed = _date(str(r.get("broadcast_Date") or "")[:11], "%d-%b-%Y")
        link = str(r.get("xbrl") or "")
        basis = str(r.get("consolidated") or "").strip().lower()
        if not q or basis not in ("consolidated", "standalone") or not link.lower().endswith(".xml"):
            continue
        out.append({"quarter": q, "basis": basis, "xbrl": link, "filed": filed or q,
                    "broadcast": str(r.get("broadcast_Date") or ""), "name": str(r.get("cmName") or "").strip()})
    return out


def pick(filings, standalone=False):
    """The newest QUARTERS quarters on one basis, newest first; a revised filing replaces the original.

    Consolidated by default; a company with no consolidated filings is read standalone."""
    basis = "standalone" if standalone else "consolidated"
    if not any(f["basis"] == basis for f in filings):
        basis = "consolidated" if standalone else "standalone"
    best = {}
    for f in filings:
        if f["basis"] != basis:
            continue
        old = best.get(f["quarter"])
        if old is None or (f["filed"], f["broadcast"]) > (old["filed"], old["broadcast"]):
            best[f["quarter"]] = f
    return [best[q] for q in sorted(best, reverse=True)[:QUARTERS]]


def parse_xbrl(text):
    """One quarter's XBRL -> {period_end, FIELD: float}, from the quarter's own context (no dimensions)."""
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        raise ResultsError("not an XBRL file (%s), probably a block page" % e)
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    end = None
    for el in root:
        if local(el) == "DateOfEndOfReportingPeriod" and el.text:
            end = _date(el.text, "%Y-%m-%d")
            break
    if end is None:
        raise ResultsError("the XBRL file has no DateOfEndOfReportingPeriod")
    best, best_len = None, None
    for el in root:
        if local(el) != "context" or el.find(".//{*}segment") is not None or el.find(".//{*}scenario") is not None:
            continue
        s, e = el.find(".//{*}startDate"), el.find(".//{*}endDate")
        if s is None or e is None or _date(e.text, "%Y-%m-%d") != end:
            continue
        n = (end - (_date(s.text, "%Y-%m-%d") or end)).days
        if best_len is None or n < best_len:
            best, best_len = el.get("id"), n
    if best is None:
        raise ResultsError("the XBRL file has no context for the quarter ending %s" % end)
    out = {"period_end": end}
    for el in root:
        if el.get("contextRef") == best and local(el) in FIELDS:
            try:
                out[local(el)] = float(el.text)
            except (TypeError, ValueError):
                pass
    return out


def figures(f):
    """Facts -> {period_end, revenue, net_profit, eps, operating_profit, bank}."""
    bank = "RevenueFromOperations" not in f and "InterestEarned" in f
    rev = f.get("InterestEarned") if bank else f.get("RevenueFromOperations")
    profit = f.get("ProfitOrLossAttributableToOwnersOfParent",
                   f.get("ProfitLossForPeriod", f.get("ProfitLossForThePeriod")))
    eps = f.get("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                f.get("BasicEarningsPerShareAfterExtraordinaryItems"))
    op = None
    if not bank and None not in (f.get("ProfitBeforeTax"), f.get("FinanceCosts"), f.get("OtherIncome")):
        op = f["ProfitBeforeTax"] + f["FinanceCosts"] - f["OtherIncome"]
    return {"period_end": f["period_end"], "revenue": rev, "net_profit": profit, "eps": eps,
            "operating_profit": op, "bank": bank}


def _months_back(d, n):
    """The quarter end n months before d (30 Sep - 3 = 30 Jun, 31 Mar - 3 = 31 Dec)."""
    y, m = d.year, d.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    nxt = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1)


def growth(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def pct(a, b):
    return None if a is None or not b else round(a / b * 100, 1)


def fy_label(d):
    """30 Sep 2026 -> 'Q2 FY27' (the Indian financial year ends in March)."""
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
    fy = d.year + 1 if d.month > 3 else d.year
    return ("Q%d FY%02d" % (q, fy % 100)) if q else d.isoformat()


def metrics(symbol, name, basis, quarters, filed):
    """Per-quarter figures (newest first) -> one metrics row for trader/metrics.json."""
    by_end = {q["period_end"]: q for q in quarters}
    q0 = quarters[0]
    end = q0["period_end"]
    prev, year = by_end.get(_months_back(end, 3)), by_end.get(_months_back(end, 12))
    run = [by_end.get(_months_back(end, 3 * i)) for i in range(4)]
    ttm = lambda k: (round(sum(q[k] for q in run), 2) if all(q and q[k] is not None for q in run) else None)
    row = {"symbol": symbol, "name": name, "basis": basis, "period_end": end.isoformat(), "quarter": fy_label(end),
           "filed": filed.isoformat(), "bank": q0["bank"],
           "revenue": q0["revenue"], "net_profit": q0["net_profit"], "eps": q0["eps"],
           "operating_margin": pct(q0["operating_profit"], q0["revenue"]),
           "net_margin": pct(q0["net_profit"], q0["revenue"]),
           "revenue_growth_yoy": growth(q0["revenue"], year and year["revenue"]),
           "revenue_growth_qoq": growth(q0["revenue"], prev and prev["revenue"]),
           "net_profit_growth_yoy": growth(q0["net_profit"], year and year["net_profit"]),
           "net_profit_growth_qoq": growth(q0["net_profit"], prev and prev["net_profit"]),
           "eps_growth_yoy": growth(q0["eps"], year and year["eps"]),
           "revenue_ttm": ttm("revenue"), "net_profit_ttm": ttm("net_profit"), "eps_ttm": ttm("eps"),
           "source": "NSE integrated filing (financials)"}
    return row


def fetch(symbol, client=None, offline=None, standalone=False):
    """One stock -> its metrics row. Raises ResultsError or nse errors."""
    if offline:
        doc = nse.read_json_file(os.path.join(offline, "results-%s.json" % symbol))
    else:
        doc = client.get_json(LIST_URL % urllib.parse.quote(symbol, safe=""))
    picked = pick(parse_list(doc, symbol), standalone)
    if not picked:
        raise ResultsError("NSE lists no integrated-filing results (from April 2025 on)")
    quarters = []
    for f in picked:
        if offline:
            text = nse.read_file(os.path.join(offline, f["xbrl"].rsplit("/", 1)[-1]))
        else:
            text = client.get_text(f["xbrl"], cookie=False)
        try:
            quarters.append(figures(parse_xbrl(text)))
        except ResultsError as e:
            if client is not None:
                client.forget(f["xbrl"])
            raise ResultsError("%s: %s" % (f["xbrl"], e))
    quarters.sort(key=lambda q: q["period_end"], reverse=True)
    return metrics(symbol, picked[0]["name"], picked[0]["basis"], quarters, picked[0]["filed"])


def _cr(x):
    return "-" if x is None else inr(round(x / 1e7)) + " cr"


def _g(x):
    return "n/a" if x is None else "%+.1f%%" % x


def render(rows, errors, blocked):
    lines = []
    for r in rows:
        lines.append("%s  %s (%s, %s%s)" % (r["symbol"], r["quarter"], r["period_end"], r["basis"],
                                            ", bank" if r["bank"] else ""))
        lines.append("    revenue     %s  (%s YoY, %s QoQ)" % (_cr(r["revenue"]), _g(r["revenue_growth_yoy"]),
                                                              _g(r["revenue_growth_qoq"])))
        lines.append("    net profit  %s  (%s YoY, %s QoQ)" % (_cr(r["net_profit"]), _g(r["net_profit_growth_yoy"]),
                                                              _g(r["net_profit_growth_qoq"])))
        lines.append("    EPS         %s  (%s YoY)   TTM EPS %s" % (
            "-" if r["eps"] is None else "Rs %.2f" % r["eps"], _g(r["eps_growth_yoy"]),
            "n/a" if r["eps_ttm"] is None else "Rs %.2f" % r["eps_ttm"]))
        lines.append("    margins     operating %s, net %s" % (
            "n/a" if r["operating_margin"] is None else "%.1f%%" % r["operating_margin"],
            "n/a" if r["net_margin"] is None else "%.1f%%" % r["net_margin"]))
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("Reported numbers from NSE filings, not a forecast. Not financial advice.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Quarterly results from NSE filings (trader-analyst).")
    ap.add_argument("--symbols", nargs="*", help="default: Kite holdings and trader/targets.json")
    ap.add_argument("--standalone", action="store_true", help="read standalone results instead of consolidated")
    ap.add_argument("--offline", metavar="DIR", help="read results-<SYMBOL>.json and the XBRL files from DIR")
    ap.add_argument("--kite-dir", default=kite_snapshot.DIR)
    ap.add_argument("--targets", default="trader/targets.json")
    ap.add_argument("--write", nargs="?", const="trader/metrics.json", metavar="PATH",
                    help="save the rows for the screener (default trader/metrics.json)")
    ap.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows, errors, blocked = [], [], []
    try:
        now = nse_calendar.parse_now(a.now)
        symbols = []
        for s in (a.symbols or watchlist.watch_list(a.kite_dir, a.targets)):
            n = nse_symbols.normalize(s)
            if n not in symbols:
                symbols.append(n)
        if not symbols:
            raise ResultsError("which stocks? pass --symbols INFY TCS, or save Kite holdings / write trader/targets.json")
        client = None if a.offline else nse.Client()
        for sym in symbols:
            try:
                rows.append(fetch(sym, client, a.offline, a.standalone))
            except nse.NseBlocked as e:
                blocked.append("%s (save results-%s.json and each XBRL file it links to in one folder, then rerun "
                               "with --offline <folder>)" % (e, sym))
            except (ResultsError, nse.NseError) as e:
                errors.append("%s: %s" % (sym, e))
        if a.write:
            d = os.path.dirname(a.write)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(a.write, "w", encoding="utf-8") as fh:
                json.dump({"as_of": now.isoformat(), "complete": not (errors or blocked), "errors": errors,
                           "blocked": blocked, "companies": rows}, fh, indent=2)
                fh.write("\n")
    except (ResultsError, nse.NseError, nse_calendar.CalendarError, nse_symbols.SymbolError,
            watchlist.WatchError) as e:
        print("results.py: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # never let a scheduled run look like success on a crash
        print("results.py: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({"companies": rows, "errors": errors, "blocked": blocked}, indent=2))
    else:
        print(render(rows, errors, blocked))
    return 2 if (errors or blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
```

Replace `trader-analyst/metrics.example.json` with:

```json
{
  "as_of": "2026-10-27T10:00:00+05:30",
  "complete": true,
  "errors": [],
  "blocked": [],
  "companies": [
    {
      "symbol": "INFY",
      "name": "Infosys Limited",
      "basis": "consolidated",
      "period_end": "2026-09-30",
      "quarter": "Q2 FY27",
      "filed": "2026-10-23",
      "bank": false,
      "revenue": 492440000000.0,
      "net_profit": 78230000000.0,
      "eps": 19.32,
      "operating_margin": 21.0,
      "net_margin": 15.9,
      "revenue_growth_yoy": 10.7,
      "revenue_growth_qoq": 2.1,
      "net_profit_growth_yoy": 6.2,
      "net_profit_growth_qoq": 0.7,
      "eps_growth_yoy": 8.8,
      "revenue_ttm": 1893360000000.0,
      "net_profit_ttm": 307470000000.0,
      "eps_ttm": 75.69,
      "source": "NSE integrated filing (financials)"
    }
  ]
}
```

Replace `trader-analyst/SKILL.md` with:

````markdown
---
name: trader-analyst
description: >-
  The Earnings Analyst for NSE stocks. Reads the quarterly financial results
  companies file with NSE (the XBRL behind each integrated filing) and sums
  up what changed: revenue, net profit, EPS, operating and net margin, each
  against the quarter before (QoQ) and the same quarter a year earlier
  (YoY), with the trailing twelve months. Handles banks and companies that
  file only standalone results. Writes trader/metrics.json for the
  screener. Use when the user says "how were Infosys's results", "analyze
  the results", "what changed this quarter", "is revenue growing", "Q2
  numbers", "compare margins", or "run the analyst on my holdings".
argument-hint: "[symbols]"
---

# trader-analyst

Results season moves stocks, and the press release puts the best number
first. This skill reads the numbers the company actually filed with NSE,
lines up the quarters and says plainly what changed.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/results.py"                          # Kite holdings + trader/targets.json
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY TCS HDFCBANK
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --standalone
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --write   # -> trader/metrics.json
python3 "${CLAUDE_SKILL_DIR}/results.py" --symbols INFY --offline <folder>
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/kite/holdings.json`, `trader/targets.json` | the stocks to read when `--symbols` is not given |
| `trader/metrics.json` | with `--write`: one row per stock for `/trader-screener`; `complete` is false when a stock could not be read |
| `metrics.example.json` (this folder) | a real row: INFY, Q2 FY27 |

## Where the numbers come from

For each stock, NSE's integrated filing (financials) list,
`https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol=<SYMBOL>&type=Integrated%20Filing-%20Financials`,
and the XBRL file each row links to. One XBRL file is one quarter, so the
tool reads the newest five: this quarter, the quarter before, the same
quarter last year, and four in a row for TTM. NSE keeps a daily cache in
`trader/cache/nse/`. Results filed before April 2025 used NSE's older page
and are not read, so TTM and YoY need filings from mid-2025 on.

If NSE blocks a request, the tool exits 2 and names the URL. Ask the user to
open the list URL in a browser and save it as `results-<SYMBOL>.json`, then
open each XBRL link it shows (the newest five quarters) and save each file
under its own name in the same folder, and rerun with `--offline <folder>`.

## The rules

- Consolidated (the whole group) by default; `--standalone` for the parent
  company alone. A company that files only standalone is read standalone,
  and the row says `basis: standalone`.
- A revised filing replaces the original for the same quarter.
- Revenue is revenue from operations; for a bank it is interest earned.
- Net profit is the profit attributable to the company's owners when the
  filing gives it (minority interest excluded).
- Operating margin is (profit before tax + finance costs - other income) /
  revenue. It is empty for banks.
- A growth figure is empty (`n/a`) when the comparison quarter is missing,
  never guessed.
- Quarters follow the Indian financial year (April to March): 30 Sep 2026
  is Q2 FY27.

## Steps

1. Run `results.py` for the stocks the user means (exit 0 all read, 2 when
   any stock could not be read: read the error or blocked lines).
2. Lead with what changed: revenue and net profit growth YoY and QoQ, then
   margins and EPS. Say "n/a" plainly when a comparison is missing.
3. If the user wants to screen, run with `--write` and hand
   `trader/metrics.json` to `/trader-screener`.

## Example

INFY, Q2 FY27 (quarter ended 30 Sep 2026, consolidated, filed 23 Oct 2026):
revenue Rs 49,244 cr (+10.7% YoY, +2.1% QoQ), net profit Rs 7,823 cr (+6.2%
YoY, +0.7% QoQ), EPS Rs 19.32 (+8.8% YoY), TTM EPS Rs 75.69, operating
margin 21.0%, net margin 15.9%.

## What it never does

It never forecasts, never fills a missing quarter with an estimate, and
never calls a result good or bad on its own: it reports the change.

## Safety

- Education and tooling, not financial advice. Nothing here is a recommendation to buy or sell.
- Every order in this pack is a LIVE order with real money on your Zerodha account: Kite has no paper account.
- Nothing in this pack places an order except through trader-broker, and only when all three hold:
  trader-risk passed that exact order in the last 10 minutes, the user typed an explicit yes for that
  one order in the chat, and the user approved the Kite connector's order card because its order tool
  is set to "Needs approval". Never set an order tool to "Always allow".
- No F&O, no NRML, no stop-loss orders. MIS (intraday), MARKET orders, short selling and after-market
  orders stay off unless the user turns them on in trader/config.json themselves.
- Kite logins live in the connector, never in the chat or in files.
````

README lines. Each old text must match exactly once.

- In `README.md`, replace:

```
| `/trader-analyst` | Earnings Analyst | Pulls each company's reported numbers from SEC XBRL (revenue, net income, diluted EPS, margins, growth) and its latest earnings release. |
```

  with:

```
| `/trader-analyst` | Earnings Analyst | Reads each company's quarterly results filed with NSE (revenue, net profit, EPS, margins, YoY and QoQ growth, TTM) and writes the metrics the screener reads. |
```

- In `README.md`, replace:

```
python3 trader-analyst/facts.py AAPL                                   # quarters, growth, EPS
```

  with:

```
python3 trader-analyst/results.py --symbols INFY --write               # results -> trader/metrics.json
```

- In `README.md`, replace:

```
trader-analyst/    SKILL.md, facts.py, metrics.example.json
```

  with:

```
trader-analyst/    SKILL.md, results.py, metrics.example.json
```


- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_analyst.py -v`
Expected: all 16 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`. The old US copycat tests still pass, because Task 2 replaces them.

```bash
git add -A trader-analyst tests/test_analyst.py tests/fixtures/trader-analyst README.md
git commit -m "Convert trader-analyst to NSE quarterly results (integrated filing XBRL)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 2: trader-copycat for Indian investors and mutual funds

**Files:**
- Delete: `trader-copycat/{edgar13f.py,filers.json,share_classes.json}`, `tests/test_copycat.py` (the US one), `tests/fixtures/trader-copycat/` (the SEC fixtures)
- Copy (unchanged): `trader-alerts/{nse,nse_calendar,nse_symbols,rupees}.py` into `trader-copycat/`
- Create:
  - `trader-copycat/shp.py`, `trader-copycat/amc.py`, `trader-copycat/copycat.py`
  - the 11 fixture files in `tests/fixtures/trader-copycat/`
  - the new `tests/test_copycat.py`
- Replace: `trader-copycat/SKILL.md`, `trader-copycat/targets.example.json`
- Modify: `README.md` (copycat lines)

**Interfaces:**
- Consumes:
  - `nse.Client`, `nse.read_file`, `nse.read_json_file`
  - `nse_symbols.load(path).by_isin(isin) -> {symbol, name, series, isin}`
  - `rupees.inr`
  - `size.parse_weights` (trader-budget, test only)
  - `trader/prices.json` `{"as_of", "prices": {SYMBOL: price}}`, written by trader-alerts
- Produces:
  - `shp.parse_master`, `shp.parse(text) -> {symbol, company, isin, quarter, total_shares, holders: [{category, name, shares, pct}]}`, `shp.matches`, `shp.holding`, `shp.change`
  - `amc.parse(text) -> [{isin, name, quantity, value, pct}]`, `amc.is_equity`, `amc.change`
  - `copycat.investor(name, symbols, client=None, offline=None) -> (rows, absent, errors, blocked)`
  - `copycat.fund(path, previous, master) -> (rows, unmapped)`
  - The `trader/targets.json` shape: `{kind, source, as_of, written, method, weights: [{symbol, name, weight, ...}]}`, which `size.parse_weights` reads.

- [ ] **Step 1: Remove the SEC version and write the fixtures**

```bash
git rm -q trader-copycat/edgar13f.py trader-copycat/filers.json trader-copycat/share_classes.json tests/test_copycat.py
git rm -q -r tests/fixtures/trader-copycat
```

The `shp-*.json` lists are real NSE answers (the two newest quarters). The `SHP_*.xml` files are real, trimmed to the named shareholders, and labelled. The `PAC_` rows are kept on purpose. `fund-oct.csv` and `fund-sep.csv` are synthetic sheets in an AMC layout, labelled in their first row.

`tests/fixtures/trader-copycat/SHP_1691163_13072026115115_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1691163_13072026115115_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_OtherNonInstitutions_Context18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherNonInstitutionsAxis"><in-bse-shp:OtherNonInstitutionsDomain>OtherNonInstitutions_Context18</in-bse-shp:OtherNonInstitutionsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="OtherNonInstitutions_Context18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherNonInstitutionsAxis"><in-bse-shp:OtherNonInstitutionsDomain>OtherNonInstitutions_Context18</in-bse-shp:OtherNonInstitutionsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic15</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic15</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic16</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic16</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic17</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic17</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic18</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic18</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public19"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic19</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public19"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic19</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">NCC</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE868B01028</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">NCC LIMITED</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-06-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">627846588</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">ICICI PRUDENTIAL SMALLCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">38877833</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.0619</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">QUANT MUTUAL FUND - QUANT MULTI CAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">31338509</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0499</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context17">BANDHAN INFRASTRUCTURE FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="shares">6288522</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="pure">0.01</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">TATA AIA LIFE INSURANCE CO LTD-PENSION EQUITY FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">13950733</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.0222</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">66733266</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.1063</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_OtherNonInstitutions_Context18">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="OtherNonInstitutions_Context18" decimals="INF" unitRef="shares">11600000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="OtherNonInstitutions_Context18" decimals="INF" unitRef="pure">0.0185</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public15">RARE shares &amp; Stocks Private Ltd</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public15" decimals="INF" unitRef="shares">298000</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public16">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public16" decimals="INF" unitRef="shares">66733266</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public17">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public17" decimals="INF" unitRef="shares">11600000</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public18">Estate of Late Mr.Rakesh Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public18" decimals="INF" unitRef="shares">1896666</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public19">Rajesh Kumar Radheshyam Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public19" decimals="INF" unitRef="shares">25000</in-bse-shp:NumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/SHP_1694281_16072026043845_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1694281_16072026043845_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByOtherInstitutionsForeign_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignAxis"><in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain>DetailsOfSharesHeldByOtherInstitutionsForeign_Context15</in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignAxis"><in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain>DetailsOfSharesHeldByOtherInstitutionsForeign_Context15</in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_ProvidentFundsOrPensionFunds_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByProvidentFundsOrPensionFundsAxis"><in-bse-shp:ProvidentFundsOrPensionFundsDomain>ProvidentFundsOrPensionFunds_Context15</in-bse-shp:ProvidentFundsOrPensionFundsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="ProvidentFundsOrPensionFunds_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByProvidentFundsOrPensionFundsAxis"><in-bse-shp:ProvidentFundsOrPensionFundsDomain>ProvidentFundsOrPensionFunds_Context15</in-bse-shp:ProvidentFundsOrPensionFundsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">TITAN</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE280A01028</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">TITAN COMPANY LIMITED</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-06-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">887786160</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">Sbi Nifty 50 Etf</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">15999057</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.018</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">Icici Prudential Balanced Advantage Fund</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">11184971</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0126</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context17">Uti Nifty 50 Etf</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="shares">9851148</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="pure">0.0111</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">Life Insurance Corporation Of India</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">19224672</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.0217</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByOtherInstitutionsForeign_Context15">Foreign Institutional Investors</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15" decimals="INF" unitRef="shares">12000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15" decimals="INF" unitRef="pure">0</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_ProvidentFundsOrPensionFunds_Context15">Nps Trust A/C Uti Pension Fund Limited-Scheme State Govt</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="ProvidentFundsOrPensionFunds_Context15" decimals="INF" unitRef="shares">15386048</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ProvidentFundsOrPensionFunds_Context15" decimals="INF" unitRef="pure">0.0173</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">37643895</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.0424</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16" decimals="INF" unitRef="shares">9540575</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16" decimals="INF" unitRef="pure">0.0107</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/SHP_1698042_21072026022318_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1698042_21072026022318_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context16</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context16</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500092</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-06-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">CRISIL</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE007A01025</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">Crisil Limited</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-06-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">73130017</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">KOTAK LARGE &amp; MIDCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">786404</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.0108</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">SBI MIDCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">1762971</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0241</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">GENERAL INSURANCE CORPORATION OF INDIA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">2288374</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.0313</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context16">LICI ASM NON PAR</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context16" decimals="INF" unitRef="shares">991756</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context16" decimals="INF" unitRef="pure">0.0136</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">3799000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.0519</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/SHP_1733674_07102026121837_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1733674_07102026121837_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context17</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneAxis"><in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneDomain>DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15</in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneAxis"><in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneDomain>DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15</in-bse-shp:DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOneDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_OtherNonInstitutions_Context18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherNonInstitutionsAxis"><in-bse-shp:OtherNonInstitutionsDomain>OtherNonInstitutions_Context18</in-bse-shp:OtherNonInstitutionsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="OtherNonInstitutions_Context18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherNonInstitutionsAxis"><in-bse-shp:OtherNonInstitutionsDomain>OtherNonInstitutions_Context18</in-bse-shp:OtherNonInstitutionsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic15</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic15</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic16</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic16</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic17</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public17"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic17</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic18</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public18"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic18</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_PAC_Public19"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic19</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="PAC_Public19"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500294</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicAxis"><in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain>DetailsOfTheShareholdersActingAsPersonsInConcertForPublic19</in-bse-shp:DetailsOfTheShareholdersActingAsPersonsInConcertForPublicDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">NCC</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE868B01028</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">NCC Limited</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-09-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">627846588</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">ICICI PRUDENTIAL SMALLCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">36441380</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.058</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">QUANT MUTUAL FUND - QUANT MULTI CAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">31338509</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0499</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context17">BANDHAN INFRASTRUCTURE FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="shares">7113785</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context17" decimals="INF" unitRef="pure">0.0113</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15">ISHARES CORE MSCI EMERGING MARKETS ETF</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15" decimals="INF" unitRef="shares">6339128</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByInstitutionsForeignPortfolioInvestorOne_Context15" decimals="INF" unitRef="pure">0.0101</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">TATA AIA LIFE INSURANCE CO LTD-PENSION EQUITY FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">14462734</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.023</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">66733266</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.1063</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_OtherNonInstitutions_Context18">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="OtherNonInstitutions_Context18" decimals="INF" unitRef="shares">11600000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="OtherNonInstitutions_Context18" decimals="INF" unitRef="pure">0.0185</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public15">RARE shares &amp; Stocks Private Ltd</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public15" decimals="INF" unitRef="shares">298000</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public16">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public16" decimals="INF" unitRef="shares">66733266</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public17">Rekha Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public17" decimals="INF" unitRef="shares">11600000</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public18">Estate of Late Mr.Rakesh Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public18" decimals="INF" unitRef="shares">1896666</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_PAC_Public19">Rajesh Kumar Radheshyam Jhunjhunwala</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="PAC_Public19" decimals="INF" unitRef="shares">25000</in-bse-shp:NumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/SHP_1738880_15102026035926_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1738880_15102026035926_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByOtherInstitutionsForeign_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignAxis"><in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain>DetailsOfSharesHeldByOtherInstitutionsForeign_Context15</in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignAxis"><in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain>DetailsOfSharesHeldByOtherInstitutionsForeign_Context15</in-bse-shp:DetailsOfSharesHeldByOtherInstitutionsForeignDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_ProvidentFundsOrPensionFunds_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByProvidentFundsOrPensionFundsAxis"><in-bse-shp:ProvidentFundsOrPensionFundsDomain>ProvidentFundsOrPensionFunds_Context15</in-bse-shp:ProvidentFundsOrPensionFundsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="ProvidentFundsOrPensionFunds_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByProvidentFundsOrPensionFundsAxis"><in-bse-shp:ProvidentFundsOrPensionFundsDomain>ProvidentFundsOrPensionFunds_Context15</in-bse-shp:ProvidentFundsOrPensionFundsDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/ScripCode">500114</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">TITAN</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE280A01028</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">TITAN COMPANY LIMITED</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-09-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">887786160</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">UTI-FLEXI CAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">9549187</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.0108</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">Sbi Nifty 50 Etf</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">16405430</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0185</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">Life Insurance Corporation of India</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">19177264</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.0216</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByOtherInstitutionsForeign_Context15">Foreign Institutional Investors</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15" decimals="INF" unitRef="shares">12000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByOtherInstitutionsForeign_Context15" decimals="INF" unitRef="pure">0</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_ProvidentFundsOrPensionFunds_Context15">NPS TRUST A/C - LIC PENSION FUND LIMITED - NPS LITE SCHEME - GOVT. PATTERN</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="ProvidentFundsOrPensionFunds_Context15" decimals="INF" unitRef="shares">15850348</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ProvidentFundsOrPensionFunds_Context15" decimals="INF" unitRef="pure">0.0179</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">37643895</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.0424</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16" decimals="INF" unitRef="shares">9540575</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context16" decimals="INF" unitRef="pure">0.0107</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/SHP_1742882_21102026034110_WEB.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Trimmed for tests from https://nsearchives.nseindia.com/corporate/xbrl/SHP_1742882_21102026034110_WEB.xml (fetched 2026-10-27): only the facts the parser reads are kept. -->
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-shp="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp" xmlns:in-bse-shp-types="http://www.bseindia.com/xbrl/shp/2025-10-31/in-bse-shp-types" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:negated="http://www.xbrl.org/2009/role/negated" xmlns:net="http://www.xbrl.org/2009/role/net" xmlns:nonnum="http://www.xbrl.org/dtr/type/non-numeric" xmlns:num="http://www.xbrl.org/dtr/type/numeric" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:xbrldt="http://xbrl.org/2005/xbrldt" xmlns:xl="http://www.xbrl.org/2003/XLink" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<xbrli:context id="MainD"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="MainI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="ShareholdingPattern_ContextI"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="in-bse-shp:CategoryOfShareholdersAxis">in-bse-shp:ShareholdingPatternMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context15</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="MutualFundsOrUTI_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByMutualFundsOrUTIAxis"><in-bse-shp:MutualFundsOrUTIDomain>MutualFundsOrUTI_Context16</in-bse-shp:MutualFundsOrUTIDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context15</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_InsuranceCompanies_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context16</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="InsuranceCompanies_Context16"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByInsuranceCompaniesAxis"><in-bse-shp:InsuranceCompaniesDomain>InsuranceCompanies_Context16</in-bse-shp:InsuranceCompaniesDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:context id="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15"><xbrli:entity><xbrli:identifier scheme="http://www.bseindia.com/in-bse-shp/Symbol">CRISIL</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:typedMember dimension="in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhAxis"><in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain>DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15</in-bse-shp:DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakhDomain></xbrldi:typedMember></xbrli:scenario></xbrli:context>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<xbrli:unit id="shares"><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>
<in-bse-shp:Symbol contextRef="MainD">CRISIL</in-bse-shp:Symbol>
<in-bse-shp:ISIN contextRef="MainD">INE007A01025</in-bse-shp:ISIN>
<in-bse-shp:NameOfTheCompany contextRef="MainD">Crisil Limited</in-bse-shp:NameOfTheCompany>
<in-bse-shp:DateOfReport contextRef="MainI">2026-09-30</in-bse-shp:DateOfReport>
<in-bse-shp:NumberOfShares contextRef="ShareholdingPattern_ContextI" decimals="INF" unitRef="shares">73130017</in-bse-shp:NumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context15">SBI MIDCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="shares">1590569</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context15" decimals="INF" unitRef="pure">0.0217</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_MutualFundsOrUTI_Context16">KOTAK LARGE &amp; MIDCAP FUND</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="shares">974752</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="MutualFundsOrUTI_Context16" decimals="INF" unitRef="pure">0.0133</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context15">GENERAL INSURANCE CORPORATION OF INDIA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="shares">2288374</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context15" decimals="INF" unitRef="pure">0.0313</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_InsuranceCompanies_Context16">LICI ASM NON PAR</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="InsuranceCompanies_Context16" decimals="INF" unitRef="shares">991756</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="InsuranceCompanies_Context16" decimals="INF" unitRef="pure">0.0136</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
<in-bse-shp:NameOfTheShareholder contextRef="D_DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15">REKHA JHUNJHUNWALA</in-bse-shp:NameOfTheShareholder>
<in-bse-shp:NumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="shares">3799000</in-bse-shp:NumberOfShares>
<in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="DetailsOfSharesHeldByResidentIndividualShareholdersHoldingNominalShareCapitalInExcessOfRsTwoLakh_Context15" decimals="INF" unitRef="pure">0.0519</in-bse-shp:ShareholdingAsAPercentageOfTotalNumberOfShares>
</xbrli:xbrl>
```

`tests/fixtures/trader-copycat/fund-oct.csv`:

```csv
Synthetic test sheet in the layout AMCs use for monthly portfolios (not a real fund),,,,,,
Example Flexi Cap Fund,,,,,,
Portfolio as on 31-Oct-2026,,,,,,
,,,,,,
Sr. No.,Name of the Instrument,ISIN,Industry / Rating,Quantity,Market value (Rs. in Lakhs),% to Net Assets
,Equity & Equity related,,,,,
,(a) Listed / awaiting listing on Stock Exchanges,,,,,
1,HDFC Bank Limited,INE040A01034,Banks,"52,10,000","1,02,345.67",8.12%
2,Infosys Limited,INE009A01021,IT - Software,"41,00,000","61,500.00",4.88%
3,Reliance Industries Limited,INE002A01018,Petroleum Products,"30,50,000","42,700.50",3.39%
4,Mahindra & Mahindra Limited,INE101A01026,Automobiles,"9,80,000","31,360.00",2.49%
5,ITC Limited,INE154A01025,Diversified FMCG,"60,00,000","24,600.00",1.95%
6,Bajaj Auto Limited,INE917I01010,Automobiles,"1,10,000","9,900.00",0.79%
7,Infosys Limited,INE009A01021,IT - Software,"1,00,000","1,500.00",0.12%
,Sub Total,,,,"2,73,906.17",21.74%
,(b) Foreign Securities,,,,,
8,Alphabet Inc A,US02079K3059,Internet,"1,20,000","20,300.00",1.61%
,Debt Instruments,,,,,
9,7.80% HDFC Bank Ltd NCD (MD 03/05/2033),INE040A08AB1,CRISIL AAA,500,"5,050.00",0.40%
,TREPS,,,,"18,200.00",1.44%
,Net Receivables / (Payables),,,,"(1,250.00)",(0.10%)
,GRAND TOTAL,,,,"12,60,000.00",100.00%
```

`tests/fixtures/trader-copycat/fund-sep.csv`:

```csv
Synthetic test sheet in the layout AMCs use for monthly portfolios (not a real fund),,,,,,
Example Flexi Cap Fund,,,,,,
Portfolio as on 30-Sep-2026,,,,,,
,,,,,,
Sr. No.,Name of the Instrument,ISIN,Industry / Rating,Quantity,Market value (Rs. in Lakhs),% to Net Assets
,Equity & Equity related,,,,,
1,HDFC Bank Limited,INE040A01034,Banks,"50,00,000","98,000.00",7.95%
2,Infosys Limited,INE009A01021,IT - Software,"45,00,000","66,000.00",5.36%
3,Reliance Industries Limited,INE002A01018,Petroleum Products,"30,50,000","41,900.00",3.40%
4,Tata Consultancy Services Limited,INE467B01029,IT - Software,"6,00,000","24,000.00",1.95%
5,ITC Limited,INE154A01025,Diversified FMCG,"60,00,000","24,000.00",1.95%
6,Bajaj Auto Limited,INE917I01010,Automobiles,"1,10,000","9,800.00",0.80%
,GRAND TOTAL,,,,"12,32,000.00",100.00%
```

`tests/fixtures/trader-copycat/shp-CRISIL.json`:

```json
[
 {
  "broadcastDate": "21-OCT-2026 15:41:15",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-SEP-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE007A01017",
  "name": "Crisil Limited",
  "newColumn": true,
  "pr_and_prgrp": "66.64",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "33.36",
  "recordId": "216036",
  "remarksWeb": "We have been informed by the Promoter Entity Standard & Poor's Internatonal LLC, that they are in the process of updating their PAN in their Demat Account. The correct PAN of the Entity is AAOCS0557M.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "21-OCT-2026",
  "symbol": "CRISIL",
  "systemDate": "21-OCT-2026 15:41:25",
  "timeDifference": "00:00:10",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1742882_21102026034110_WEB.xml",
  "xbrlFileSize": "1.21 MB"
 },
 {
  "broadcastDate": "21-JUL-2026 14:23:23",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-JUN-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE007A01017",
  "name": "Crisil Limited",
  "newColumn": true,
  "pr_and_prgrp": "66.64",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "33.36",
  "recordId": "212666",
  "remarksWeb": "We have been informed by the Promoter Entity Standard & Poor's Internatonal LLC, that they are in the process of updating their PAN in their Demat Account. The correct PAN of the Entity is AAOCS0557M.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "21-JUL-2026",
  "symbol": "CRISIL",
  "systemDate": "21-JUL-2026 14:23:28",
  "timeDifference": "00:00:05",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1698042_21072026022318_WEB.xml",
  "xbrlFileSize": "1.33 MB"
 }
]
```

`tests/fixtures/trader-copycat/shp-NCC.json`:

```json
[
 {
  "broadcastDate": "07-OCT-2026 12:18:42",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-SEP-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE868B01010",
  "name": "NCC Limited",
  "newColumn": true,
  "pr_and_prgrp": "23.19",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "76.81",
  "recordId": "213358",
  "remarksWeb": "1.The Promoter and Promoter Group constitutes of 32 members, of which 3 members do not hold any shares.      2.During the quarter, the Shareholding of Promoter and Promoter Group has been increased by  657401 Eq. Shares (from 144927495 to 145584896 Eq.Shares)  by market purchase.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "07-OCT-2026",
  "symbol": "NCC",
  "systemDate": "07-OCT-2026 12:18:48",
  "timeDifference": "00:00:06",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1733674_07102026121837_WEB.xml",
  "xbrlFileSize": "278.47 KB"
 },
 {
  "broadcastDate": "13-JUL-2026 11:51:20",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-JUN-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE868B01010",
  "name": "NCC Limited",
  "newColumn": true,
  "pr_and_prgrp": "23.08",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "76.92",
  "recordId": "210885",
  "remarksWeb": "1.The Promoter and Promoter Group constitutes of 32 members, of which 3 members do not hold any shares.  2.During the quarter, the Shareholding of Promoter and Promoter Group has been increased by  1697648 Eq. Shares (from 143229847 to 144927495 Eq.Shares)  by market purchase.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "13-JUL-2026",
  "symbol": "NCC",
  "systemDate": "13-JUL-2026 11:51:24",
  "timeDifference": "00:00:04",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1691163_13072026115115_WEB.xml",
  "xbrlFileSize": "273.81 KB"
 }
]
```

`tests/fixtures/trader-copycat/shp-TITAN.json`:

```json
[
 {
  "broadcastDate": "15-OCT-2026 15:59:39",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-SEP-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0.1",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE280A01010",
  "name": "Titan Company Limited",
  "newColumn": true,
  "pr_and_prgrp": "52.9",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "47",
  "recordId": "214611",
  "remarksWeb": "1.Tata Sons Private Limited (TSPL) holds 20.84 % in the Company. However, TSPL being a Core Investment Company, is exempt from compliance of Companies (Significant Beneficial Owners) Rules, 2018 on the investments made by TSPL.   2.Tata AIA Life Insurance Company Limited is not considered part of Promoter Group and holds 12,63,113 equity shares of the Company representing 0.14% of the paid-up capital as on 30th  June 2026. Accordingly, holding of Tata AIA Life Insurance Company Limited is included under Public Shareholding under the head Institutions (Domestic)- Insurance companies.   3. Kaleyra Africa (Pty) Limited, ceased to be the Promoter Group Entity w.e.f. September 4, 2026, as the entity was dissolved due to voluntary liquidation.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "15-OCT-2026",
  "symbol": "TITAN",
  "systemDate": "15-OCT-2026 15:59:43",
  "timeDifference": "00:00:04",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1738880_15102026035926_WEB.xml",
  "xbrlFileSize": "1.58 MB"
 },
 {
  "broadcastDate": "16-JUL-2026 16:38:55",
  "cgTimeStamp": null,
  "countString": null,
  "date": "30-JUN-2026",
  "desc": "NEW_1",
  "employeeTrusts": "0.05",
  "format": null,
  "index": "-",
  "industry": "-",
  "isin": "INE280A01010",
  "name": "Titan Company Limited",
  "newColumn": true,
  "pr_and_prgrp": "52.9",
  "promoterDematNotes": "",
  "publicShareholdingNotes": "",
  "public_val": "47.05",
  "recordId": "211500",
  "remarksWeb": "1.Tata Sons Private Limited (TSPL) holds 20.84 % in the Company. However, TSPL being a Core Investment Company, is exempt from compliance of Companies (Significant Beneficial Owners) Rules, 2018 on the investments made by TSPL. 2.Tata AIA Life Insurance Company Limited is not considered part of Promoter Group and holds 11,98,886 equity shares of the Company representing 0.14 % of the paid-up capital as on 30th  June 2026. Accordingly, holding of Tata AIA Life Insurance Company Limited is included under Public Shareholding under the head Institutions (Domestic)- Insurance companies. 3. Smart Value Homes (New Project) LLP, ceased to be the Promoter Group Entity w.e.f. June 16, 2026, as the entity was struck off. 4. TCS Solution Center SA, ceased to be the Promoter Group Entity w.e.f. April 1, 2026, as the entity merged with TCS Uruguay S.A. 5. TSBB Voice Private Limited, ceased to be the Promoter Group Entity w.e.f. May 12, 2026, as the entity was struck off.",
  "revisedData": "N",
  "revisedDate": null,
  "revisedRemark": null,
  "revisedStatus": "-",
  "revisionDate": null,
  "revisionRemark": null,
  "shareholdingPatternNotes": "",
  "submissionDate": "16-JUL-2026",
  "symbol": "TITAN",
  "systemDate": "16-JUL-2026 16:39:04",
  "timeDifference": "00:00:09",
  "typeOfSubmission": null,
  "underlyingDrs": null,
  "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/SHP_1694281_16072026043845_WEB.xml",
  "xbrlFileSize": "1.55 MB"
 }
]
```


- [ ] **Step 2: Write the failing tests**

`tests/test_copycat.py`:

```python
import datetime
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from _load import load, FIX

cc = load("trader-copycat", "copycat")
shp = cc.shp
amc = cc.amc
size = load("trader-budget", "size")

CDIR = os.path.join(FIX, "trader-copycat")
SYMS = os.path.join(FIX, "trader-alerts", "EQUITY_L-sample.csv")
NOW = "2026-10-27T10:00"
TITAN_Q2 = "SHP_1738880_15102026035926_WEB.xml"
NCC_Q2 = "SHP_1733674_07102026121837_WEB.xml"
OCT = os.path.join(CDIR, "fund-oct.csv")
SEP = os.path.join(CDIR, "fund-sep.csv")


def read(name):
    with open(os.path.join(CDIR, name), encoding="utf-8") as fh:
        return fh.read()


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cc.main(argv)
    return code, out.getvalue(), err.getvalue()


class Shareholding(unittest.TestCase):
    def test_titan_two_accounts_add_up(self):
        doc = shp.parse(read(TITAN_Q2))
        self.assertEqual((doc["symbol"], doc["quarter"], doc["total_shares"]),
                         ("TITAN", datetime.date(2026, 9, 30), 887786160))
        h = shp.holding(doc, "Rekha Jhunjhunwala")
        self.assertEqual((h["shares"], h["pct"], h["names"]), (47184470, 5.31, ["REKHA JHUNJHUNWALA"]))

    def test_persons_acting_in_concert_are_not_counted_twice(self):
        h = shp.holding(shp.parse(read(NCC_Q2)), "rekha jhunjhunwala")
        self.assertEqual((h["shares"], h["pct"]), (66733266 + 11600000, 12.48))

    def test_name_matching(self):
        self.assertTrue(shp.matches("Rakesh Jhunjhunwala", "Estate of Late Mr.Rakesh Jhunjhunwala"))
        self.assertFalse(shp.matches("Rekha Jhunjhunwala", "Rajesh Kumar Radheshyam Jhunjhunwala"))
        self.assertFalse(shp.matches("", "Anyone"))

    def test_master_newest_first_and_errors(self):
        got = shp.parse_master(json.loads(read("shp-TITAN.json")), "TITAN")
        self.assertEqual([g["quarter"] for g in got], [datetime.date(2026, 9, 30), datetime.date(2026, 6, 30)])
        with self.assertRaises(shp.ShpError):
            shp.parse_master({"data": []}, "TITAN")
        with self.assertRaises(shp.ShpError):
            shp.parse("<html>blocked")

    def test_quarter_changes(self):
        h = lambda n: {"shares": n}
        self.assertEqual([shp.change(h(5), None), shp.change(None, h(5)), shp.change(h(6), h(5)),
                          shp.change(h(4), h(5)), shp.change(h(5), h(5))],
                         ["new", "gone", "added", "trimmed", "same"])


class FundSheet(unittest.TestCase):
    def test_october_sheet(self):
        rows = {r["isin"]: r for r in amc.parse(read("fund-oct.csv"))}
        self.assertEqual(len(rows), 6)
        infy = rows["INE009A01021"]
        self.assertEqual((round(infy["pct"], 2), infy["quantity"]), (5.0, 4200000.0))
        for skipped in ("US02079K3059", "INE040A08AB1"):
            self.assertNotIn(skipped, rows)

    def test_equity_isins(self):
        self.assertEqual([amc.is_equity(i) for i in ("INE009A01021", "INE040A08AB1", "US02079K3059", "", "INE009A0102")],
                         [True, False, False, False, False])

    def test_fractions_become_percent_and_no_quantity_compares_pct(self):
        rows = amc.parse("Company Name,ISIN,% of NAV\nInfosys,INE009A01021,0.06\nTCS,INE467B01029,0.04\n")
        self.assertEqual([r["pct"] for r in rows], [6.0, 4.0])
        self.assertEqual(amc.change(rows[0], dict(rows[0], pct=5.0)), "added")

    def test_not_a_portfolio_sheet(self):
        with self.assertRaises(amc.AmcError):
            amc.parse("Date,Symbol,Price\n2026-10-01,INFY,1500\n")


class Investor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prices = os.path.join(self.tmp.name, "prices.json")
        self.out = os.path.join(self.tmp.name, "targets.json")
        self.price({"TITAN": 3400.0, "CRISIL": 5100.0, "NCC": 290.0})

    def tearDown(self):
        self.tmp.cleanup()

    def price(self, p):
        with open(self.prices, "w") as fh:
            json.dump({"as_of": "2026-10-27T15:30:00+05:30", "prices": p}, fh)

    def cc(self, *args):
        return run(["investor", "Rekha Jhunjhunwala", "--offline", CDIR, "--prices", self.prices, "--now", NOW]
                   + list(args))

    def test_weights_by_holding_value_and_budget_reads_them(self):
        code, text, _ = self.cc("--symbols", "TITAN", "CRISIL", "NCC", "--write", self.out)
        self.assertEqual(code, 0)
        self.assertIn("NCC         7,83,33,266 shares  12.48% of the company  same", text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual(doc["kind"], "investor")
        self.assertEqual([(w["symbol"], w["weight"]) for w in doc["weights"]],
                         [("TITAN", 79.22), ("NCC", 11.22), ("CRISIL", 9.57)])
        self.assertIn("partial portfolio", doc["method"])
        self.assertEqual([r["ticker"] for r in size.parse_weights(doc)], ["TITAN", "NCC", "CRISIL"])

    def test_someone_not_named(self):
        code, text, _ = run(["investor", "Radhakishan Damani", "--symbols", "TITAN", "--offline", CDIR,
                             "--prices", self.prices, "--now", NOW])
        self.assertEqual(code, 0)
        self.assertIn("TITAN      not named (holds under 1%, or none)", text)
        self.assertIn("nobody named 'Radhakishan Damani' in any of these patterns", text)

    def test_missing_price_refuses_to_write(self):
        self.price({"TITAN": 3400.0})
        code, text, _ = self.cc("--symbols", "TITAN", "NCC", "--write", self.out)
        self.assertEqual(code, 2)
        self.assertIn("no price for NCC", text)
        self.assertIn("not written: no price for NCC", text)
        self.assertFalse(os.path.exists(self.out))

    def test_partial_read_refuses_to_write(self):
        code, text, _ = self.cc("--symbols", "TITAN", "INFY", "--write", self.out)
        self.assertEqual(code, 2)
        self.assertIn("error: INFY: cannot read", text)
        self.assertIn("not written: 1 stock(s) could not be read", text)
        self.assertFalse(os.path.exists(self.out))


class Fund(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "targets.json")

    def tearDown(self):
        self.tmp.cleanup()

    def cc(self, *args):
        return run(["fund", "Example Flexi Cap", "--file", OCT, "--previous", SEP, "--symbols-file", SYMS,
                    "--now", "2026-11-05T10:00", "--write", self.out] + list(args))

    def test_top_four_with_changes(self):
        code, text, _ = self.cc("--top", "4")
        self.assertEqual(code, 0)
        for line in ("HDFCBANK     8.12% of NAV  added     weight 42.74", "INFY         5.00% of NAV  trimmed",
                     "M&M          2.49% of NAV  new", "TCS          0.00% of NAV  sold"):
            self.assertIn(line, text)
        with open(self.out) as fh:
            doc = json.load(fh)
        self.assertEqual([(w["symbol"], w["weight"]) for w in doc["weights"]],
                         [("HDFCBANK", 42.74), ("INFY", 26.32), ("RELIANCE", 17.84), ("M&M", 13.11)])
        self.assertAlmostEqual(sum(r["weight"] for r in size.parse_weights(doc)), 100, delta=0.05)

    def test_unlisted_stock_inside_the_top_refuses_to_write(self):
        code, text, _ = self.cc("--top", "5")
        self.assertEqual(code, 2)
        self.assertIn("not written: ITC Limited would be in the copied holdings", text)
        self.assertFalse(os.path.exists(self.out))

    def test_missing_symbol_list(self):
        code, _, err = run(["fund", "X", "--file", OCT, "--symbols-file", os.path.join(self.tmp.name, "none.csv"),
                            "--now", NOW])
        self.assertEqual(code, 2)
        self.assertIn("nse_symbols.py refresh", err)


class Network(unittest.TestCase):
    def test_symbol_is_encoded_and_a_block_page_is_forgotten(self):
        master = json.loads(read("shp-TITAN.json"))

        class Client:
            urls, forgot = [], []

            def get_json(self, url, cache=True):
                self.urls.append(url)
                return master

            def get_text(self, url, cookie=True, cache=True):
                return "<html>Access Denied"

            def forget(self, url):
                self.forgot.append(url)
        c = Client()
        rows, absent, errors, blocked = cc.investor("Rekha Jhunjhunwala", ["M&M"], c)
        self.assertTrue(c.urls[0].endswith("symbol=M%26M"))
        self.assertEqual((rows, len(errors), len(c.forgot)), ([], 1, 1))

    def test_blocked_names_the_offline_fallback(self):
        class Client:
            def get_json(self, url, cache=True):
                raise cc.nse.NseBlocked(url, "HTTP 403")
        rows, absent, errors, blocked = cc.investor("Rekha Jhunjhunwala", ["TITAN"], Client())
        self.assertIn("--offline", blocked[0])
        self.assertIn("symbol=TITAN", blocked[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `python3 -m unittest discover -s tests -p test_copycat.py -v`
Expected: an ERROR, because `trader-copycat/copycat.py` does not exist.

- [ ] **Step 4: Implement**

```bash
cp trader-alerts/nse.py trader-alerts/nse_calendar.py trader-alerts/nse_symbols.py trader-alerts/rupees.py trader-copycat/
```

`trader-copycat/shp.py`:

```python
"""NSE shareholding patterns for trader-copycat: who holds more than 1% of a company.

Every quarter each listed company files its shareholding pattern with NSE as XBRL. The pattern names every
public shareholder with more than 1% of the company (and every promoter), with their share count. NSE lists
the filings per stock at

    https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=<SYMBOL>

and each row links to the XBRL file (https://nsearchives.nseindia.com/corporate/xbrl/SHP_..._WEB.xml).

In the XBRL a shareholder's name sits on a context named D_<Category>_ContextN and the shares and the
percentage on the matching <Category>_ContextN. One person can appear more than once (two accounts, or two
categories): the holding is the sum. The PAC_ contexts repeat holdings already counted (persons acting in
concert) and are skipped. Standard library only.
"""

import datetime
import re
import xml.etree.ElementTree as ET

MASTER_URL = "https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=%s"


class ShpError(Exception):
    pass


def parse_master(doc, symbol):
    """NSE's shareholding list -> [{quarter (date), xbrl}], newest quarter first."""
    if not isinstance(doc, list):
        raise ShpError("the shareholding list for %s is not NSE's answer (not a list)" % symbol)
    out = {}
    for r in doc:
        if not isinstance(r, dict):
            continue
        try:
            q = datetime.datetime.strptime(str(r.get("date")).strip(), "%d-%b-%Y").date()
        except ValueError:
            continue
        link = str(r.get("xbrl") or "")
        if link.lower().endswith(".xml") and q not in out:
            out[q] = link
    return [{"quarter": q, "xbrl": out[q]} for q in sorted(out, reverse=True)]


def _category(ctx):
    c = re.sub(r"_?Context\d+$", "", ctx)
    return c[len("DetailsOfSharesHeldBy"):] if c.startswith("DetailsOfSharesHeldBy") else c


def parse(text):
    """One shareholding XBRL -> {symbol, company, isin, quarter, total_shares, holders: [{category, name, shares, pct}]}.

    pct is a percentage of the company (4.24 for 4.24%)."""
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        raise ShpError("not an XBRL file (%s), probably a block page" % e)
    local = lambda el: el.tag.rsplit("}", 1)[-1]
    head, names, facts = {}, {}, {}
    for el in root:
        n, c, v = local(el), el.get("contextRef") or "", (el.text or "").strip()
        if n in ("Symbol", "NameOfTheCompany", "DateOfReport", "ISIN") and n not in head and not c.startswith("D_"):
            head[n] = v
        elif n == "NameOfTheShareholder" and c.startswith("D_") and not c.startswith("D_PAC"):
            names.setdefault(c[2:], " ".join(v.split()))
        elif n in ("NumberOfShares", "ShareholdingAsAPercentageOfTotalNumberOfShares"):
            facts.setdefault(c, {})[n] = v
    try:
        quarter = datetime.datetime.strptime(head.get("DateOfReport", ""), "%Y-%m-%d").date()
    except ValueError:
        raise ShpError("the shareholding XBRL has no DateOfReport")
    holders = []
    for ctx, name in names.items():
        f = facts.get(ctx, {})
        try:
            shares = int(float(f["NumberOfShares"]))
            pct = round(float(f["ShareholdingAsAPercentageOfTotalNumberOfShares"]) * 100, 2)
        except (KeyError, ValueError):
            continue
        holders.append({"category": _category(ctx), "name": name, "shares": shares, "pct": pct})
    total = facts.get("ShareholdingPattern_ContextI", {}).get("NumberOfShares")
    return {"symbol": head.get("Symbol", "").upper(), "company": head.get("NameOfTheCompany", ""),
            "isin": head.get("ISIN", ""), "quarter": quarter,
            "total_shares": int(float(total)) if total else None, "holders": holders}


def words(name):
    return set(re.findall(r"[a-z0-9]+", str(name).lower()))


def matches(query, name):
    """Every word of the query is a word of the name: 'rekha jhunjhunwala' matches 'REKHA JHUNJHUNWALA'."""
    q = words(query)
    return bool(q) and q <= words(name)


def holding(doc, query):
    """The query's total holding in one pattern -> {shares, pct, names, categories}, or None if not named."""
    hits = [h for h in doc["holders"] if matches(query, h["name"])]
    if not hits:
        return None
    return {"shares": sum(h["shares"] for h in hits), "pct": round(sum(h["pct"] for h in hits), 2),
            "names": sorted({h["name"] for h in hits}), "categories": sorted({h["category"] for h in hits})}


def change(now, before):
    """Quarter-on-quarter: new, added, trimmed, same, or gone (sold, or now under 1% and no longer named)."""
    if now and not before:
        return "new"
    if before and not now:
        return "gone"
    if now["shares"] > before["shares"]:
        return "added"
    if now["shares"] < before["shares"]:
        return "trimmed"
    return "same"
```

`trader-copycat/amc.py`:

```python
"""Mutual fund portfolios for trader-copycat, from the monthly sheet the fund house (AMC) publishes.

Every AMC publishes each scheme's full portfolio every month on its website, usually as an Excel sheet. The
user opens it, picks the scheme's sheet and saves it as CSV. Sheets differ between AMCs, so the parser finds
the header row by its column names (ISIN, the instrument or company name, quantity, market value, % to NAV
or % to net assets, matched case-insensitively) and keeps only equity shares of Indian companies: an ISIN
starting with INE whose security code (characters 8 and 9) is 01. Bonds, debentures and commercial paper
from the same companies (INE... with another code), cash, TREPS, derivatives and foreign stocks are
skipped, and so is any row without a % to NAV. Standard library only.
"""

import csv
import io
import re

NAME = ("name of the instrument", "name of instrument", "instrument", "company name", "name of the issuer",
        "issuer", "security", "name")
PCT = ("% to nav", "% of nav", "% to net assets", "% of net assets", "% to aum", "% of aum", "% to net asset",
       "% of net asset", "percentage to nav", "% nav")
QTY = ("quantity", "no. of shares", "shares", "qty")
VALUE = ("market value", "market/fair value", "fair value", "value")


class AmcError(Exception):
    pass


def _norm(cell):
    return " ".join(str(cell or "").lower().replace("\n", " ").split())


def _col(header, names):
    for want in names:
        for i, h in enumerate(header):
            if h == want or h.startswith(want + " ") or h.startswith(want + "("):
                return i
    return None


def _num(text):
    t = str(text or "").replace(",", "").replace("%", "").strip()
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1]
    try:
        return float(t)
    except ValueError:
        return None


def is_equity(isin):
    isin = str(isin or "").strip().upper()
    return bool(re.match(r"^INE[A-Z0-9]{4}01[A-Z0-9]{3}$", isin))


def parse(text):
    """CSV text -> [{isin, name, quantity, value, pct}] for the equity rows, pct as a percentage of NAV."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    header_at, cols = None, None
    for i, r in enumerate(rows):
        h = [_norm(c) for c in r]
        isin, pct = _col(h, ("isin", "isin code", "isin no.")), _col(h, PCT)
        if isin is not None and pct is not None:
            header_at = i
            cols = {"isin": isin, "pct": pct, "name": _col(h, NAME), "qty": _col(h, QTY), "value": _col(h, VALUE)}
            break
    if header_at is None:
        raise AmcError("no header row with an ISIN column and a %% to NAV column (is this the AMC's portfolio sheet "
                       "saved as CSV?)")
    cell = lambda r, k: r[cols[k]] if cols[k] is not None and cols[k] < len(r) else ""
    out = []
    for r in rows[header_at + 1:]:
        isin = cell(r, "isin").strip().upper()
        pct = _num(cell(r, "pct"))
        if not is_equity(isin) or pct is None:
            continue
        out.append({"isin": isin, "name": " ".join(cell(r, "name").split()), "quantity": _num(cell(r, "qty")),
                    "value": _num(cell(r, "value")), "pct": pct})
    if not out:
        raise AmcError("the sheet has a header row but no equity rows (INE...01... ISINs with a %% to NAV)")
    if max(x["pct"] for x in out) <= 1 and sum(x["pct"] for x in out) <= 1.01:
        for x in out:  # the sheet gives fractions (0.0523), not percentages (5.23)
            x["pct"] = round(x["pct"] * 100, 4)
    merged = {}
    for x in out:  # one stock can appear twice (two lots, or a pending listing); add them up
        m = merged.get(x["isin"])
        if m is None:
            merged[x["isin"]] = dict(x)
        else:
            m["pct"] += x["pct"]
            for k in ("quantity", "value"):
                m[k] = None if m[k] is None or x[k] is None else m[k] + x[k]
    return list(merged.values())


def change(now, before):
    """Month-on-month by quantity (or % to NAV when a sheet has no quantity): new, added, trimmed, same, sold."""
    if now and not before:
        return "new"
    if before and not now:
        return "sold"
    k = "quantity" if now["quantity"] is not None and before["quantity"] is not None else "pct"
    if now[k] > before[k]:
        return "added"
    if now[k] < before[k]:
        return "trimmed"
    return "same"
```

`trader-copycat/copycat.py`:

```python
#!/usr/bin/env python3
"""Copy an Indian investor or a mutual fund for trader-copycat, and write trader/targets.json.

    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC
    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC --write
    python3 copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN NCC --offline DIR
    python3 copycat.py fund "Parag Parikh Flexi Cap" --file portfolio.csv
    python3 copycat.py fund "Parag Parikh Flexi Cap" --file oct.csv --previous sep.csv --top 10 --write

investor: an individual's holdings are public only where they own more than 1% of a company, in that
company's quarterly shareholding pattern on NSE. There is no list of everything one person owns, so you
name the stocks (--symbols) and the tool reads each one's two newest patterns (shp.py). The result is a
partial portfolio: stakes under 1% never show. Weights come from the value of each holding (shares x price
from trader/prices.json, which /trader-alerts writes from Kite quotes).

fund: a mutual fund's full portfolio, from the monthly sheet its AMC publishes, saved as CSV (amc.py).
Weights come from % to NAV. ISINs are matched to NSE symbols with the NSE symbol list
(nse_symbols.py refresh); unmatched stocks are listed and left out.

Both scale the chosen holdings (--top N, default 10; 0 for all) to 100 and show what changed since the
quarter (or month) before: new, added, trimmed, same, and gone or sold. --write saves trader/targets.json
for /trader-budget and /trader-rebalance.

Exit code 0 when everything was read, 2 when any stock could not be read, a price is missing, or NSE
blocked a request (the message names the URL and how to rerun with --offline). --write refuses to save
weights built from a partial read.

This is someone else's portfolio, disclosed after the fact. Copying it is your own decision: not financial
advice.
"""

import argparse
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import amc
import nse
import nse_calendar
import nse_symbols
import shp
from rupees import inr


class CopyError(Exception):
    pass


def load_prices(path):
    if not path or not os.path.exists(path):
        return {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as e:
        raise CopyError("%s is not valid JSON: %s" % (path, e))
    prices = doc.get("prices") if isinstance(doc, dict) else None
    if not isinstance(prices, dict):
        raise CopyError("%s has no prices object (write it with trader-alerts: alerts.py quote ... --write)" % path)
    out = {}
    for k, v in prices.items():
        try:
            out[str(k).upper()] = float(v)
        except (TypeError, ValueError):
            pass
    return out, doc.get("as_of")


def scale(rows, key, top):
    """Keep the top N rows by key (0 = all) and add weight = share of their total, scaled to 100."""
    held = sorted([r for r in rows if r.get(key)], key=lambda r: r[key], reverse=True)
    if top:
        held = held[:top]
    total = sum(r[key] for r in held)
    for r in held:
        r["weight"] = round(r[key] / total * 100, 2) if total else 0.0
    return held


def investor(name, symbols, client=None, offline=None):
    """-> (rows, absent, errors, blocked). A row: {symbol, company, quarter, shares, pct, before, change, names}."""
    rows, absent, errors, blocked = [], [], [], []
    for sym in symbols:
        try:
            if offline:
                master = nse.read_json_file(os.path.join(offline, "shp-%s.json" % sym))
            else:
                master = client.get_json(shp.MASTER_URL % urllib.parse.quote(sym, safe=""))
            quarters = shp.parse_master(master, sym)[:2]
            if not quarters:
                raise shp.ShpError("NSE lists no shareholding patterns")
            docs = []
            for q in quarters:
                if offline:
                    text = nse.read_file(os.path.join(offline, q["xbrl"].rsplit("/", 1)[-1]))
                else:
                    text = client.get_text(q["xbrl"], cookie=False)
                try:
                    docs.append(shp.parse(text))
                except shp.ShpError as e:
                    if client is not None:
                        client.forget(q["xbrl"])
                    raise shp.ShpError("%s: %s" % (q["xbrl"], e))
            now = shp.holding(docs[0], name)
            before = shp.holding(docs[1], name) if len(docs) > 1 else None
            if not now and not before:
                absent.append(sym)
                continue
            rows.append({"symbol": sym, "company": docs[0]["company"], "quarter": docs[0]["quarter"].isoformat(),
                         "shares": now["shares"] if now else 0, "pct": now["pct"] if now else 0.0,
                         "before": before["shares"] if before else 0,
                         "change": shp.change(now, before) if len(docs) > 1 else "new",
                         "names": (now or before)["names"]})
        except nse.NseBlocked as e:
            blocked.append("%s (save shp-%s.json and the two newest XBRL files it links to in one folder, then "
                           "rerun with --offline <folder>)" % (e, sym))
        except (shp.ShpError, nse.NseError) as e:
            errors.append("%s: %s" % (sym, e))
    return rows, absent, errors, blocked


def fund(path, previous, master):
    """-> (rows, unmapped). A row: {symbol, name, isin, pct, quantity, before, change}; sold rows have pct 0.

    unmapped: [{isin, name, pct}] for equity rows whose ISIN is not on the NSE symbol list."""
    now = {r["isin"]: r for r in amc.parse(nse.read_file(path))}
    before = {r["isin"]: r for r in amc.parse(nse.read_file(previous))} if previous else {}
    rows, unmapped = [], []
    for isin in list(now) + [i for i in before if i not in now]:
        n, b = now.get(isin), before.get(isin)
        hit = master.by_isin(isin)
        if hit is None:
            if n:
                unmapped.append({"isin": isin, "name": n["name"], "pct": n["pct"]})
            continue
        rows.append({"symbol": hit["symbol"], "name": (n or b)["name"] or hit["name"], "isin": isin,
                     "pct": n["pct"] if n else 0.0, "quantity": n["quantity"] if n else 0,
                     "before": (b["quantity"] if b and b["quantity"] is not None else (b["pct"] if b else 0)),
                     "change": amc.change(n, b) if previous else "-"})
    return rows, unmapped


def write_targets(path, doc):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Copy an investor or a mutual fund into trader/targets.json.")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("investor", help="an individual's >1%% stakes from NSE shareholding patterns")
    p.add_argument("name", help='the name as filed, e.g. "Rekha Jhunjhunwala"')
    p.add_argument("--symbols", nargs="+", required=True, help="the stocks to look in")
    p.add_argument("--offline", metavar="DIR", help="read shp-<SYMBOL>.json and the XBRL files from DIR")
    p.add_argument("--prices", default="trader/prices.json")
    f = sub.add_parser("fund", help="a mutual fund's monthly portfolio sheet saved as CSV")
    f.add_argument("name", help='the scheme, e.g. "Parag Parikh Flexi Cap"')
    f.add_argument("--file", required=True, help="this month's portfolio sheet as CSV")
    f.add_argument("--previous", help="last month's sheet as CSV, to show what changed")
    f.add_argument("--symbols-file", default=nse_symbols.CACHE, help="NSE EQUITY_L.csv (nse_symbols.py refresh)")
    for x in (p, f):
        x.add_argument("--top", type=int, default=10, help="copy the N biggest holdings (0 = all, default 10)")
        x.add_argument("--write", nargs="?", const="trader/targets.json", metavar="PATH",
                       help="save the weights (default trader/targets.json)")
        x.add_argument("--now", help="pretend it is this time (ISO, IST; tests only, needs TRADER_TEST_CLOCK=1)")
        x.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 2
    errors, blocked, lines, refused = [], [], [], False
    try:
        now = nse_calendar.parse_now(a.now)
        if a.top < 0:
            raise CopyError("--top must be 0 (all) or more")
        if a.cmd == "investor":
            symbols = []
            for s in a.symbols:
                n = nse_symbols.normalize(s)
                if n not in symbols:
                    symbols.append(n)
            rows, absent, errors, blocked = investor(a.name, symbols, None if a.offline else nse.Client(), a.offline)
            prices, prices_at = load_prices(a.prices)
            missing = [r["symbol"] for r in rows if r["shares"] and r["symbol"] not in prices]
            for r in rows:
                r["value"] = round(r["shares"] * prices[r["symbol"]], 2) if r["symbol"] in prices else None
            chosen = scale(rows, "value", a.top) if not missing else []
            quarters = sorted({r["quarter"] for r in rows if r["shares"]})
            lines.append("%s in NSE shareholding patterns (stakes above 1%% only), quarter ended %s" % (
                a.name, ", ".join(quarters) or "-"))
            for r in sorted(rows, key=lambda r: (-(r["value"] or 0), -r["shares"], r["symbol"])):
                w = next((c["weight"] for c in chosen if c is r), None)
                lines.append("  %-10s %12s shares  %5.2f%% of the company  %-8s %s%s" % (
                    r["symbol"], inr(r["shares"])[3:], r["pct"], r["change"],
                    inr(r["value"]) if r["value"] is not None else "no price",
                    ("  weight %.2f" % w) if w is not None else ""))
            for s in absent:
                lines.append("  %-10s not named (holds under 1%%, or none)" % s)
            if absent and not rows and not errors and not blocked:
                lines.append("nobody named %r in any of these patterns: names match word by word, so check the name "
                             "as the company filed it (the SKILL.md example shows how)" % a.name)
            if missing:
                lines.append("no price for %s: save Kite quotes and run trader-alerts' alerts.py quote %s --write, "
                             "then rerun" % (", ".join(missing), " ".join(missing)))
            doc = {"kind": "investor", "source": "%s in NSE shareholding patterns, quarter ended %s (%s)" % (
                       a.name, ", ".join(quarters), ", ".join(r["symbol"] for r in chosen)),
                   "as_of": quarters[-1] if quarters else None, "written": now.isoformat(),
                   "method": "holding value (shares x price from %s as of %s), top %s scaled to 100; only stakes "
                             "above 1%% are disclosed, so this is a partial portfolio" % (a.prices, prices_at,
                                                                                           a.top or "all"),
                   "weights": [{"symbol": r["symbol"], "name": r["company"], "weight": r["weight"],
                                "shares": r["shares"], "pct_of_company": r["pct"], "value": r["value"],
                                "change": r["change"]} for r in chosen]}
        else:
            master = nse_symbols.load(a.symbols_file)
            rows, unmapped = fund(a.file, a.previous, master)
            chosen = scale(rows, "pct", a.top)
            lines.append("%s: %d stocks in the sheet, copying the top %d by %% to NAV" % (
                a.name, len([r for r in rows if r["pct"]]) + len(unmapped), len(chosen)))
            for r in sorted(rows, key=lambda r: (-r["pct"], r["symbol"])):
                w = next((c["weight"] for c in chosen if c is r), None)
                lines.append("  %-10s %6.2f%% of NAV  %-8s%s" % (r["symbol"], r["pct"], r["change"],
                                                               ("  weight %.2f" % w) if w is not None else ""))
            cutoff = chosen[-1]["pct"] if chosen and a.top else 0
            crowded = [u for u in unmapped if u["pct"] >= cutoff]
            for u in unmapped:
                lines.append("  %-10s %6.2f%% of NAV  not on the NSE symbol list, left out: %s %s" % (
                    "?", u["pct"], u["isin"], u["name"]))
            doc = {"kind": "fund", "source": "%s portfolio sheet %s" % (a.name, os.path.basename(a.file)),
                   "as_of": now.date().isoformat(), "written": now.isoformat(),
                   "method": "%% to NAV, top %s scaled to 100" % (a.top or "all"),
                   "weights": [{"symbol": r["symbol"], "name": r["name"], "weight": r["weight"], "isin": r["isin"],
                                "pct_of_nav": r["pct"], "change": r["change"]} for r in chosen]}
        if a.write:
            why = None
            if errors or blocked:
                why = "%d stock(s) could not be read, so the weights would be wrong" % (len(errors) + len(blocked))
            elif a.cmd == "investor" and missing:
                why = "no price for %s" % ", ".join(missing)
            elif a.cmd == "fund" and crowded:
                why = ("%s would be in the copied holdings but is not on the NSE symbol list (run nse_symbols.py "
                       "refresh, or pick a smaller --top)" % ", ".join(u["name"] or u["isin"] for u in crowded))
            elif not doc["weights"]:
                raise CopyError("nothing to copy: no holding to weight")
            if why:
                refused = True
                lines.append("not written: %s" % why)
            else:
                write_targets(a.write, doc)
                lines.append("wrote %s (%d weights)" % (a.write, len(doc["weights"])))
    except (CopyError, amc.AmcError, shp.ShpError, nse.NseError, nse_calendar.CalendarError,
            nse_symbols.SymbolError) as e:
        print("copycat.py: %s" % e, file=sys.stderr)
        return 2
    except Exception as e:  # never let a crash look like success
        print("copycat.py: unexpected %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    for e in errors:
        lines.append("error: " + e)
    for b in blocked:
        lines.append("blocked: " + b)
    lines.append("Someone else's portfolio, disclosed after the fact. Not financial advice.")
    if a.json:
        print(json.dumps(dict(doc, rows=rows, errors=errors, blocked=blocked), indent=2, default=str))
    else:
        print("\n".join(lines))
    return 2 if (errors or blocked or refused or (a.cmd == "investor" and missing)) else 0


if __name__ == "__main__":
    sys.exit(main())
```

Replace `trader-copycat/targets.example.json` with:

```json
{
  "_note": "Example: real shareholdings for the quarter ended 30 Sep 2026; the prices are illustrative.",
  "kind": "investor",
  "source": "Rekha Jhunjhunwala in NSE shareholding patterns, quarter ended 2026-09-30 (TITAN, NCC, CRISIL)",
  "as_of": "2026-09-30",
  "written": "2026-10-27T10:00:00+05:30",
  "method": "holding value (shares x price from trader/prices.json as of 2026-10-27T15:30:00+05:30), top 10 scaled to 100; only stakes above 1% are disclosed, so this is a partial portfolio",
  "weights": [
    {
      "symbol": "TITAN",
      "name": "TITAN COMPANY LIMITED",
      "weight": 79.22,
      "shares": 47184470,
      "pct_of_company": 5.31,
      "value": 160427198000.0,
      "change": "same"
    },
    {
      "symbol": "NCC",
      "name": "NCC Limited",
      "weight": 11.22,
      "shares": 78333266,
      "pct_of_company": 12.48,
      "value": 22716647140.0,
      "change": "same"
    },
    {
      "symbol": "CRISIL",
      "name": "Crisil Limited",
      "weight": 9.57,
      "shares": 3799000,
      "pct_of_company": 5.19,
      "value": 19374900000.0,
      "change": "same"
    }
  ]
}
```

Replace `trader-copycat/SKILL.md` with:

````markdown
---
name: trader-copycat
description: >-
  The Reverse Engineer for Indian investors and mutual funds. For a famous
  individual investor, reads the quarterly NSE shareholding pattern of each
  stock you name and finds their stakes above 1% (the only stakes India
  makes public), with what they added, trimmed or dropped since the quarter
  before. For a mutual fund, reads the monthly portfolio sheet the fund
  house publishes (saved as CSV) with what changed since last month. Turns
  either into weights and writes trader/targets.json for /trader-budget.
  Use when the user says "copy Rekha Jhunjhunwala", "what does Damani own
  in", "copy Parag Parikh Flexi Cap", "copy this fund's top 10", "what did
  the fund buy this month", or names an Indian investor or a scheme.
argument-hint: "investor NAME --symbols ... | fund NAME --file sheet.csv"
---

# trader-copycat

Copying starts with what India makes public. A listed company names every
shareholder with more than 1% of it in its quarterly shareholding pattern.
A mutual fund publishes its whole portfolio every month. This skill reads
both and turns them into weights you can size.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC
python3 "${CLAUDE_SKILL_DIR}/copycat.py" investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC --write
python3 "${CLAUDE_SKILL_DIR}/copycat.py" fund "Parag Parikh Flexi Cap" --file oct.csv --previous sep.csv --top 10 --write
python3 "${CLAUDE_SKILL_DIR}/nse_symbols.py" refresh          # the NSE symbol list the fund command needs
```

## What it reads and writes

| file | what |
| --- | --- |
| `trader/prices.json` | investor: prices for the value weights (written by `/trader-alerts` from Kite quotes) |
| `trader/cache/nse/EQUITY_L.csv` | fund: NSE's symbol list, to turn ISINs into symbols (`nse_symbols.py refresh`) |
| `trader/targets.json` | with `--write`: the weights for `/trader-budget` and `/trader-rebalance` |
| `targets.example.json` (this folder) | a real example: Rekha Jhunjhunwala in TITAN, NCC and CRISIL |

## An investor

There is no list of everything one person owns. The user names the stocks
to look in (`--symbols`). For each one the tool reads NSE's two newest
shareholding patterns,
`https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol=<SYMBOL>`
and the XBRL file each links to, and adds up every entry carrying the
investor's name (one person often holds through two accounts). Entries that
only repeat a holding (persons acting in concert) are not counted twice.

- The name matches when every word of it appears in the filed name, so
  "Rekha Jhunjhunwala" matches "REKHA JHUNJHUNWALA" but not "Rajesh
  Jhunjhunwala". Use the name as filed.
- "not named" means the investor holds under 1% of that company, or none.
  "gone" means named last quarter but not now: sold, or fell under 1%.
- Weights are holding value (shares x price) scaled to 100. Save Kite
  quotes for the symbols and run `alerts.py quote <symbols> --write` first;
  without a price the tool shows the holdings but writes nothing.
- This is always a partial portfolio. Say so.

If NSE blocks a request, the tool exits 2 and names the URL. Ask the user
to open it in a browser, save it as `shp-<SYMBOL>.json`, open the two
newest XBRL links it shows and save each under its own name in the same
folder, and rerun with `--offline <folder>`.

## A mutual fund

The user downloads the scheme's monthly portfolio from the fund house's
website (an Excel file), opens the scheme's sheet and saves it as CSV. The
tool finds the header row by its column names (ISIN, instrument, quantity,
market value, % to NAV or % to net assets) and keeps only equity shares of
Indian companies. It skips bonds and debentures of the same companies,
TREPS, cash, derivatives and foreign stocks. Weights are % to NAV of the
top N holdings (`--top`, default 10; 0 for all) scaled to 100. `--previous`
with last month's sheet shows new, added, trimmed and sold.

A stock whose ISIN is not on the NSE list is shown and left out. If it
would have been in the top N, nothing is written: refresh the symbol list
(`nse_symbols.py refresh`) or pick a smaller `--top`.

## Steps

1. Ask who to copy: an investor (and which stocks) or a fund (and its
   sheet as CSV).
2. Run `copycat.py` without `--write` and show the holdings, the changes
   and the weights. Exit 0 means everything was read; 2 means something
   could not be read or priced: read the error, blocked or "not written"
   lines.
3. When the user is happy, rerun with `--write`. It refuses to save weights
   built from a partial read.
4. Hand over to `/trader-budget` to size the weights to their money. Every
   order still goes through `/trader-risk` and `/trader-broker`.

## Example

Rekha Jhunjhunwala, quarter ended 30 Sep 2026: TITAN 4,71,84,470 shares
(5.31% of the company, two accounts), NCC 7,83,33,266 shares (12.48%, two
categories; the repeated concert entries are not counted twice), CRISIL
37,99,000 shares (5.19%). All three unchanged since June. At the example
prices, TITAN is 79.22% of the copy, NCC 11.22% and CRISIL 9.57%.

## What it never does

It never guesses a holding under 1%, never writes weights from a partial
read, and never places an order.

## Safety

- Education and tooling, not financial advice. Nothing here is a recommendation to buy or sell.
- Every order in this pack is a LIVE order with real money on your Zerodha account: Kite has no paper account.
- Nothing in this pack places an order except through trader-broker, and only when all three hold:
  trader-risk passed that exact order in the last 10 minutes, the user typed an explicit yes for that
  one order in the chat, and the user approved the Kite connector's order card because its order tool
  is set to "Needs approval". Never set an order tool to "Always allow".
- No F&O, no NRML, no stop-loss orders. MIS (intraday), MARKET orders, short selling and after-market
  orders stay off unless the user turns them on in trader/config.json themselves.
- Kite logins live in the connector, never in the chat or in files.
````

README lines. Each old text must match exactly once.

- In `README.md`, replace:

```
| `/trader-copycat` | Reverse Engineer | Reads an investor's 13F-HR on SEC EDGAR and rebuilds their portfolio as weights you can copy, with what they bought, added, trimmed and sold since last quarter. |
```

  with:

```
| `/trader-copycat` | Reverse Engineer | Finds an Indian investor's stakes above 1% in the NSE shareholding patterns of the stocks you name, or reads a mutual fund's monthly portfolio sheet, and turns either into weights you can copy, with what was added, trimmed and sold. |
```

- In `README.md`, replace:

```
python3 trader-copycat/edgar13f.py find buffett                        # a filer's CIK
python3 trader-copycat/edgar13f.py filings 1067983                     # its 13F-HR filings
python3 trader-copycat/edgar13f.py --help                              # holdings, diff, copy
```

  with:

```
python3 trader-copycat/copycat.py investor "Rekha Jhunjhunwala" --symbols TITAN NCC # >1% stakes
python3 trader-copycat/copycat.py fund "Parag Parikh Flexi Cap" --file oct.csv      # a fund's sheet
```

- In `README.md`, replace:

```
trader-copycat/    SKILL.md, edgar13f.py, filers.json, share_classes.json, targets.example.json
```

  with:

```
trader-copycat/    SKILL.md, copycat.py, shp.py, amc.py, targets.example.json
```


- [ ] **Step 5: Run the tests and confirm they pass**

Run: `python3 -m unittest discover -s tests -p test_copycat.py -v`
Expected: all 18 tests pass. Then run `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache .`.

```bash
git add -A trader-copycat tests/test_copycat.py tests/fixtures/trader-copycat README.md
git commit -m "Convert trader-copycat to NSE shareholding patterns and AMC portfolio sheets" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


### Task 3: CLAUDE.md and the spec, with what Phase 4b found

**Files:**
- Modify: `CLAUDE.md`, `docs/superpowers/specs/2026-10-26-indian-market-design.md`

After Phase 4b no tool calls SEC, so the CLAUDE.md SEC User-Agent rule is replaced by the NSE rule. The spec records:
- the analyst's real source
- the stricter equity-ISIN rule for fund sheets

- [ ] **Step 1: Apply the replacements**

Each old text must match exactly once.

- In `CLAUDE.md`, replace:

```
and trader-news and trader-insider (NSE announcements, SEBI insider trades, bulk and block deals; trader-pelosi was renamed trader-insider).
```

  with:

```
trader-news and trader-insider (NSE announcements, SEBI insider trades, bulk and block deals; trader-pelosi was renamed trader-insider), and trader-analyst and trader-copycat (NSE results XBRL, NSE shareholding patterns, AMC portfolio sheets saved as CSV).
```

- In `CLAUDE.md`, replace:

```
- SEC calls need a `SEC_USER_AGENT` ("Name email"), from the env or `sec_user_agent` in `trader/config.json`. Ask the user for it and never invent one. Respect the existing `time.sleep` rate limits (SEC allows at most 10 requests per second).
```

  with:

```
- NSE calls go through `nse.Client` (cookie warm-up, a pause between requests, the daily cache in `trader/cache/nse/`). When NSE blocks a request, stop with exit code 2 and print the URL plus the `--file` or `--offline` rerun; never retry around a block.
```

- In `docs/superpowers/specs/2026-10-26-indian-market-design.md`, replace:

```
| trader-analyst | Quarterly results: revenue, net profit, EPS, operating margin, YoY and QoQ growth. Writes `trader/metrics.json`. | NSE financial results |
```

  with:

```
| trader-analyst | Quarterly results: revenue, net profit, EPS, operating margin, YoY and QoQ growth. Writes `trader/metrics.json`. | NSE integrated filing (financials) XBRL; the older results page stops at Dec 2024 |
```

- In `docs/superpowers/specs/2026-10-26-indian-market-design.md`, replace:

```
and skips debt, cash and derivative rows (ISINs not starting with `INE`, or rows without a % of NAV). It stays standard-library only.
```

  with:

```
and keeps only equity shares of Indian companies: an ISIN starting with `INE` whose security code (characters 8 and 9) is `01`. That skips bonds and debentures of the same companies, cash, TREPS, derivatives, foreign stocks and rows without a % of NAV. It stays standard-library only.
```


- [ ] **Step 2: Verify and commit**

Run: `python3 -m unittest discover -s tests && ruff check --select F,E9 --target-version py38 --no-cache . && ! grep -rl "$(printf '\342\200\224')" trader-* tests docs CLAUDE.md README.md`
Expected: `OK` (326 tests), then `All checks passed!`, and no file names printed.

Smoke test, outside the repo:

```bash
R=/home/ubuntu/stock-market/trader-skill; T=$(mktemp -d) && cd "$T" && export TRADER_TEST_CLOCK=1
python3 "$R/trader-analyst/results.py" --symbols INFY --offline "$R/tests/fixtures/trader-analyst" --now 2026-10-27T10:00
printf '{"prices": {"TITAN": 3400, "CRISIL": 5100, "NCC": 290}}' > p.json
python3 "$R/trader-copycat/copycat.py" investor "Rekha Jhunjhunwala" --symbols TITAN CRISIL NCC --offline "$R/tests/fixtures/trader-copycat" --prices p.json --now 2026-10-27T10:00
```

Expected:
- analyst shows INFY Q2 FY27 with revenue Rs 49,244 cr (+10.7% YoY, +2.1% QoQ) and exits 0.
- copycat shows TITAN 5.31%, NCC 12.48% and CRISIL 5.19%, with weights 79.22, 11.22 and 9.57, and exits 0.

```bash
git add CLAUDE.md docs/superpowers/specs/2026-10-26-indian-market-design.md
git commit -m "Record phase 4b sources in CLAUDE.md and the spec" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```


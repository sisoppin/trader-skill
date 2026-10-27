---
name: trader-broker
description: >-
  Order Executor for Zerodha Kite. Places APPROVED orders through the Kite
  connector, one at a time, and never without your explicit yes. Shows each
  order as a plain ticket marked LIVE ORDER, real money, with the estimated
  cost and the exact arguments for the Kite connector's place_order tool,
  records your yes word for word, then the connector's own approval card asks
  again. Covers connecting the Kite connector in Claude and setting its order
  tool to "Needs approval". Use when the user says "place the orders", "buy
  it", "execute", "send it to Zerodha", "connect Kite", or after
  /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Executor is the one place where an order can leave this pack, and
it only ever does it for one order, after one yes. The script never talks to
Kite: Claude makes the call through the Kite connector, and the connector's
approval card is the last human check.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show --index 1 --json
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" decline --index 2
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --broker-id 261026000123456
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

## Setup: the Kite connector

1. Connect Zerodha Kite in Claude's connector settings (in Claude Code,
   `/mcp`). Log in to Zerodha in the window it opens. The login stays in the connector.
2. In the connector's tool permissions, set the order tools (place, modify,
   cancel) to "Needs approval". Read tools such as quotes, holdings and
   positions can stay allowed.
3. If the user says the order tool is set to "Always allow", stop and ask
   them to change it before any order. Never place an order without that card.

## Steps, for each order

1. Run `ticket.py show --index N`. Only a READY ticket can go further: risk
   passed this exact order in the last 10 minutes and nobody decided on it.
2. Show the ticket in the chat: LIVE ORDER, real money, the plain sentence,
   the estimated cost, why.
3. Ask for a yes for that one order. Record the reply word for word with
   `ticket.py approve --index N --reply "<reply>"`. A reply that is not an
   explicit yes for this order is not recorded: ask again.
4. Call the Kite connector's `place_order` tool with exactly the arguments
   the ticket printed. The connector's card asks the user again.
5. Record what happened: `ticket.py result --index N --status placed
   --broker-id <Kite order id>`, or `denied`, or `failed` with `--note`.
6. Move to the next order. Never batch: one yes covers one order.

## What counts as a yes

"yes", "Yes, buy it", "yes 6 INFY" count. "ok", "sure", "haan", "yes to
all", "yes TCS" for an INFY ticket, a different quantity or price, a
question or a yes with a condition do not.

Any extra word or number must match this order: its symbol, side (buy or sell), product (delivery or intraday), type (limit or market), quantity, price or value. "yes 7" for a 6-share order, "yes sell" for a buy, "yes, never mind" and "yes WIPRO" are not recorded.

## Example

After trader-risk passes the four example orders, ticket 1 reads "BUY 6
shares of INFY, limit Rs 1,612.50, delivery (CNC), good for today",
estimated Rs 9,675 + Rs 11.49 charges = Rs 9,686.49 out. The user says
"yes", Claude records it, calls place_order, the user approves the card, and
`result` records Kite's order id.

## What it never does

It never places an order itself, never sends an order that is not READY,
never treats one yes as covering several orders, and never sends anything
but the exact arguments on the ticket.

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

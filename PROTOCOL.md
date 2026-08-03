# Ledger Arena: protocol specification

> This copy is a snapshot taken when the kit was published. The canonical
> version is served at **https://hiring-arena.twocc.in/protocol**, and if the
> two ever disagree, that one wins. Any clarification made in Discord is folded
> into it.

You are building a server that keeps a double-entry book of record. We stream you
a broker's event feed; you post the events into your book and send us back the
journal legs each one produced. We score correctness continuously.

**Your server competes, not you.** The stream is resumable, so a crash at 3am
costs you very little. There is nothing to stay awake for.

---

## 1. What you need

Outbound HTTPS only. You do **not** need a public address, a domain, a
certificate or a cloud account. Your server connects to ours.

Any language. Everything below is plain HTTP and JSON.

---

## 2. Accounts

| Account | Name | Type |
| --- | --- | --- |
| `1100` | Omnibus Cash at Broker | Asset |
| `1150` | Settlement Receivable | Asset |
| `1200` | Omnibus Custody | Asset |
| `2010` | Customer Wallet | Liability |
| `2100` | Customer Securities Claim | Liability |
| `2300` | Withdrawals In Transit | Liability |
| `2350` | Unsettled Trade Payable | Liability |
| `2400` | Regulatory Fees Payable | Liability |
| `2411` | Broker Fees Payable - BRK-A | Liability |
| `2412` | Broker Fees Payable - BRK-B | Liability |
| `2413` | Broker Fees Payable - BRK-C | Liability |
| `2420` | Custodian Fees Payable | Liability |
| `2430` | Partner Share Payable | Liability |
| `4000` | Brokerage Revenue | Income |
| `4010` | Custody Revenue | Income |
| `4100` | FX Spread Revenue | Income |
| `4200` | Interest Income | Income |
| `5000` | Brokerage Cost | Expense |
| `5010` | Custody Cost | Expense |
| `5100` | Partner Revenue Share | Expense |

**The firm has money of its own, and it spends money too.** Brokerage and
custody charges are the firm's income; the regulatory fee is collected on the
venue's behalf and owed onward; the executing broker, the custodian and the
introducing partner all have to be paid. So the sum of customer wallets does
**not** equal omnibus cash, and any check you write assuming it does will be
wrong on a correct book.

Revenue and cost are booked **gross**. A book that posts only the margin
balances perfectly and can never tell you what you earned or what it cost.

Every leg carries a `customer_id`. Assets increase on the debit side,
liabilities on the credit side. Debits must equal credits on every transaction.

Money has 2 decimal places. Share quantities have up to 6. **Do not use binary
floating point for money.**

---

## 3. Endpoints

Base URL and your API key are issued to you. Authenticate every request with
`Authorization: Bearer <key>`.

### `GET /v1/stream?mode=<mode>&from=<offset>`

Server-Sent Events. Each message is one event. Reconnect with the next offset
you have not processed. **Always send `from`**; the server may rewind you.

```
event: order_filled
id: 4213
data: {"offset":4213,"event_id":"evt_...","type":"order_filled","payload":{...}}
```

Three control events are not ledger events:

- `stream_open` — sent the moment you connect, before any ledger event.
  Carries your run id, how far in you are, and how long until the next
  event. Your stream is staggered against everyone else's, so the first
  event may be up to a minute and a half away; this frame is how you know
  the connection is healthy while you wait.


- `stream_reset` — reconnect, resuming from the offset in the payload. The
  server may deliberately send you events you have already seen.
- `stream_end` — the run is over.

### `POST /v1/postings?mode=<mode>`

Send one posting or a batch. Batching is strongly recommended at high rates.

```json
{"postings": [
  {"event_id": "evt_...", "legs": [
    {"account": "1100", "customer_id": "CUST-1001", "debit": "1000.00", "credit": "0.00"},
    {"account": "2010", "customer_id": "CUST-1001", "debit": "0.00", "credit": "1000.00"}
  ]}
]}
```

Maximum 500 postings per request. **The first submission for an event wins**;
later ones for the same event are ignored.

Some events correctly produce **no legs**. Send `"legs": []`. Not submitting at
all scores zero for that event.

### `POST /v1/checkpoint?mode=<mode>`

When you receive a `checkpoint_request`, reply within the stated grace period
with your full state.

```json
{
  "checkpoint_id": "cp3",
  "trial_balance": {"1100": "5913.85", "1200": "2479.00",
                    "2010": "-5913.85", "2100": "-2479.00"},
  "customers": {
    "CUST-1001": {
      "wallet_cash": "3777.53",
      "cash_hold": "320.00",
      "positions": {"ACME": {"quantity": "8", "cost_basis": "960.00"}}
    }
  },
  "open_order_routes": {"ord_9f2c11a04b3e": "BRK-B"}
}
```

`open_order_routes` maps every order you believe is still open to the broker the
routing rule sends it to. Orders you have seen filled or cancelled do not belong
here.

Trial balance values are **debit-positive**: an asset balance is positive, a
liability balance is negative.

### `GET /v1/me?mode=<mode>` and `GET /v1/leaderboard?mode=<mode>`

Your stats and the standings. In `practice` and `submission` `/v1/me` includes
a full breakdown; in `final` it does not.

### `GET /v1/rules`

The scoring weights, live. They are not a secret.

---

## 4. Posting rules

### Cash

**`deposit`** — `amount`
```
Dr 1100 amount        Cr 2010 amount
```

**`fee_charged`** — `amount`
```
Dr 2010 amount        Cr 1100 amount
```

**`withdrawal_requested`** — `withdrawal_id`, `amount`. The money has left the
customer's wallet but not yet the broker.
```
Dr 2010 amount        Cr 2300 amount
```

**`withdrawal_settled`** — `withdrawal_id`. Look up the amount from the request.
```
Dr 2300 amount        Cr 1100 amount
```

**`withdrawal_rejected`** — `withdrawal_id`. Returns it to the wallet.
```
Dr 2300 amount        Cr 2010 amount
```

**`fee_refund`** — `refunds_source_id`, `customer_id`. Refunds a fee charged
earlier. **The amount is not in this payload**: look it up from the
`fee_charged` event being refunded. Refunding the same fee twice is an error.
```
Dr 1100 amount        Cr 2010 amount
```

**`interest_credited`** — `gross_amount`, `customer_share`. Interest earned on
the omnibus balance and shared with the customer. The firm keeps the remainder,
so this is not a pass-through.
```
Dr 1100 gross         Cr 2010 customer_share
                      Cr 4200 gross - customer_share
```

**`transfer_between_customers`** — `from_customer_id`, `to_customer_id`,
`amount`. No external cash moves. Both legs land on `2010`, so **the account
nets to zero**: a book that tracks balances per account rather than per
(customer, account) will show nothing wrong at all.
```
Dr 2010 amount  (from_customer_id)
                      Cr 2010 amount  (to_customer_id)
```

### Orders

#### Routing

Every symbol belongs to one **asset class** for the whole run: `equity`, `etf`
or `bond`. No broker covers all three, and none is cheapest everywhere.

| Broker | Trades | Brokerage | Custody | Broker cost | Custody cost | Min fee | Ticket |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BRK-A` | equity, etf | 20 bps | 4 bps | 9 bps | 2 bps | 1.00 | 0.35 |
| `BRK-B` | equity, bond | 15 bps | 5 bps | 8 bps | 3 bps | 2.50 | 3.00 |
| `BRK-C` | etf, bond | 25 bps | 3 bps | 12 bps | 1 bps | 0.50 | 0.20 |

Brokerage and custody are what the **customer** is charged. Broker cost and
custody cost are what **we** are charged for the same trade. All are per unit of
principal, each rounded to the cent independently.

**The brokerage charge is floored at the broker's minimum fee**, and every fill
also costs us the broker's flat **ticket** fee whatever its size. Those two
floors pull in opposite directions: the minimum fee is revenue and the ticket is
cost, so the cheapest venue for a large order is not the cheapest for a small
one, and a small enough order loses us money however it is routed.

**Routing rule.** Route to the broker with the lowest total customer charge
(brokerage + custody) for `quantity × limit_price`, among brokers that trade
that asset class. Ties break on broker id ascending, so there is always exactly
one right answer.

You report the route of every **still-open** order at each checkpoint. Fills
name the broker that took the order, so open orders are the only place where the
routing decision is actually yours.

#### Placement

**`order_placed`** — `order_id`, `customer_id`, `side`, `symbol`, `quantity`,
`limit_price`, `asset_class`, `est_charges`.

**No legs.** A placement moves no money. It creates a *hold*: for a buy, cash of
`quantity × limit_price + est_charges` is no longer spendable; for a sell, the
shares are no longer sellable. `est_charges` covers brokerage, custody and the
regulatory fee, so holding principal alone under-reserves on every order. Holds
are reported at checkpoints, never posted.

#### Fills

**`order_partially_filled`** and **`order_filled`** — `order_id`, `customer_id`,
`side`, `symbol`, `quantity`, `price`, `principal`, `asset_class`, `broker`,
`partner_rate`, `trade_id`. An order may fill many times. `order_filled` is the
last fill and closes the order, releasing any unfilled remainder of the hold.

**The fee amounts are not in the payload.** You are given the broker and the
principal; the tariff above turns those into money. Per fill:

```
brokerage     = max(min_fee, principal x brokerage_bps)
custody       = principal x custody_bps
reg           = principal x 0.0008
broker_cost   = principal x broker_cost_bps + ticket
custody_cost  = principal x custody_cost_bps

net_revenue   = (brokerage + custody) - (broker_cost + custody_cost)
partner_share = net_revenue x partner_rate, or zero if net_revenue <= 0
```

Each is rounded to the cent **independently**, half away from zero.
`partner_rate` may be `0.50`, so a net revenue with an odd number of cents lands
exactly on a half cent. Banker's rounding and binary floating point each give a
different answer there than the rule above does.

Three things here balance perfectly when done wrong:

- **The regulatory fee is not revenue.** It is collected on the venue's behalf
  and owed onward. Crediting it to `4000` overstates income.
- **Cost is booked gross**, never netted against revenue.
- **The partner is paid on what we keep, not on what we charge.** Where cost
  exceeds revenue the share is zero: there is no clawback. That is not a corner
  case here. The ticket fee makes roughly a quarter of all fills loss-making,
  and the routing rule optimises the customer's charge, not our margin.

**Cash does not move on the trade date.** Trades settle two days later, so a
fill creates an obligation and a separate `trade_settled` event discharges it.
A book that touches `1100` here will disagree with the broker for exactly as
long as anything remains unsettled.

Buy. `241x` means the payable belonging to the broker that executed it:
```
Dr 2010 principal + brokerage      Cr 2350 principal
        + custody + reg            Cr 2100 principal
Dr 1200 principal                  Cr 4000 brokerage
Dr 5000 broker_cost                Cr 4010 custody
Dr 5010 custody_cost               Cr 2400 reg
Dr 5100 partner_share              Cr 241x broker_cost
                                   Cr 2420 custody_cost
                                   Cr 2430 partner_share
```

Sell, where `cost` is the **first-in-first-out cost of the shares sold**:
```
Dr 1150 principal                  Cr 2010 principal - brokerage
Dr 2100 cost                               - custody - reg
Dr 5000 broker_cost                Cr 1200 cost
Dr 5010 custody_cost               Cr 4000 brokerage
Dr 5100 partner_share              Cr 4010 custody
                                   Cr 2400 reg
                                   Cr 241x broker_cost
                                   Cr 2420 custody_cost
                                   Cr 2430 partner_share
```

**FIFO cost, to the cent.** A lot carries a quantity and a **total cost**. When
a sell consumes part of a lot, the cost relieved is
`round(lot_total x sold_qty / lot_qty)` and the remainder stays with the lot.
Keeping a cost *per share* and multiplying it out is also FIFO, and it will
disagree with this by a cent, so this is the convention we grade against.

**`trade_settled`** with `trade_id` discharges the obligation from that fill:
```
buy    Dr 2350 principal     Cr 1100 principal
sell   Dr 1100 principal     Cr 1150 principal
```

#### Paying it all onward

Four payables accrue a few cents per trade and are discharged in full, one
customer at a time. **The amount is never in the payload**: it is whatever has
accumulated on that account for that customer, so each of these audits every
per-trade rounding you have done since the last one. Settling an account with
nothing outstanding is an error.

| Event | Payload | Posting |
| --- | --- | --- |
| `broker_fees_settled` | `customer_id`, `broker` | Dr 241x outstanding, Cr 1100 |
| `custodian_fees_settled` | `customer_id` | Dr 2420 outstanding, Cr 1100 |
| `reg_fees_remitted` | `customer_id` | Dr 2400 outstanding, Cr 1100 |
| `partner_payout` | `customer_id` | Dr 2430 outstanding, Cr 1100 |

Realised profit and loss on a sell is
`(principal - brokerage - custody - reg) - cost`. **Never post it directly**: it
is the residual of the legs above, and a book that posts it as well double
counts every gain.

**`order_cancelled`**, **`order_rejected`** — `order_id`. **No legs.** Release
the remaining hold.

### Corporate actions

**`dividend_cash`** — `gross_amount`, `withholding_tax`, `net_amount`. Tax is
withheld at source, so only the net ever reaches us and we owe the tax to nobody.
**Do not raise a tax payable.**
```
Dr 1100 net           Cr 2010 net
```

**`dividend_reinvested`** — as above plus `reinvest_price`, `reinvest_quantity`.
The broker reinvests the net. **Cash is not involved at all.**
```
Dr 1200 net           Cr 2100 net       and add a lot of reinvest_quantity at cost net
```

**`stock_split`** — `ratio_from`, `ratio_to`. **No legs.** Quantity scales by
`ratio_to / ratio_from`; total cost is unchanged, so cost per share moves.

**`symbol_change`** — `old_symbol`, `new_symbol`. **No legs.** Re-key the holding.

### Foreign currency

**`fx_deposit`** — `amount_foreign`, `currency`, `market_rate`, `customer_rate`,
`usd_at_market_rate`, `usd_at_customer_rate`.

Money arrives in another currency and is converted. The customer is credited at
their rate; the gap between that and the market rate is the firm's spread.
Crediting the wallet with the market figure overstates what is owed to the
customer by exactly that spread.
```
Dr 1100 usd_at_market_rate     Cr 2010 usd_at_customer_rate
                               Cr 4100 the difference
```

### Corrections

**`reversal`** — `reverses_event_id`. Post the exact inverse of the original's
legs. Keep both: the audit trail retains the original and its reversal.

A reversal must also undo the original's effect on your **lot book**, not just on
the accounts. A reversed buy whose lot you leave in place will balance perfectly
and quietly corrupt every subsequent cost basis.

---

## 5. Things the stream will do to you

All of these are deliberate. None are bugs.

| | What happens | What is expected |
| --- | --- | --- |
| **Duplicates** | The same `event_id` arrives more than once | Post it once. Re-delivery must not change any balance |
| **Replay** | At an unannounced point we drop your connection and rewind you several hundred events | An idempotent consumer notices nothing |
| **Out of order** | A fill may arrive before its placement | Handle it or record it; do not stall the stream |
| **Backdated** | An event carries `backdated_days` | It still posts. Only ordering assumptions break |
| **Unknown reference** | A reversal of an event you never received | Record it as rejected, carry on |
| **Oversell** | A sale larger than the position | Reject it. **Do not** leave lots half-consumed |
| **Malformed** | A payload that will not parse | Reject it, carry on |

An event you correctly reject produces **no legs**. Submit `"legs": []`.

Three rules that would otherwise be guesswork, stated so they are not:

- **FIFO means delivery order, not trade date.** The stream is deliberately not
  date-ordered. Lots are consumed in the order the buys reached you.
- **A conflicting duplicate is not a rejection.** The same `event_id` arriving
  with *different* content is reported separately: first delivery wins.
  Rejections are events you refused to post on their own merits.
- **A redelivered event you already rejected stays one rejection**, not two. An
  id you have seen is an id you have seen, whatever you did with it.
- **A checkpoint reports your state as at the checkpoint's offset**, not as at
  the moment you reply. The grace period is for the network, not for processing
  further events first.
- **Report every account you have ever posted to**, including any that have
  netted back to zero.
- **An `fx_deposit` whose customer rate is better than the market rate is
  rejected.** A negative spread is bad data, not a gift.
- **A fill releases a proportional share of the hold that order placed**, and
  the final fill or a cancellation releases whatever remains, so a closed order
  always returns its hold to exactly zero.
- **Reversing a fill does not restore the hold.** A released hold stays
  released; a reversal undoes the postings and the lot book, not the lifecycle.

The single most expensive mistake is stopping. A server that rejects one event
and keeps consuming beats one that crashes and misses a thousand.

---

## 5b. How long this takes, and what to cut

**Budget 12 to 18 hours** if you are comfortable with double-entry bookkeeping,
more if you are meeting it for the first time. The transport is done for you in
the starter kit; all of that time is the ledger.

That is a real number, not a polite one. Reading this document carefully is an
hour of it. The fee chain and the lot book are most of the rest.

**If you run out of time, cut in this order.** These are measured against the
reference, not guessed, so you can spend your last hours where they pay:

| If you skip | You score about |
| --- | --- |
| the four settlement events | 92 |
| reversals as well | 82 |
| corporate actions as well | 64 |
| everything except cash, orders and FIFO | 51 |

Corporate actions look small and are not: a split or a reinvestment you ignore
silently corrupts every position and every cost basis after it, which is why
skipping them costs three times what skipping reversals does.

Stopping early and **writing down what is missing and how you would have done
it** costs you nothing here and reads far better than something half-built and
unexplained. We would rather see a correct book that does eight things than a
confident one that does twelve.

---

## 6. Scoring

| Component | Weight |
| --- | --- |
| Per-event posting correctness | 30 |
| Checkpoint state correctness | 40 |
| Resilience (idempotency, recovery, coverage) | 15 |
| Liveness (checkpoints on time, p95 latency) | 10 |
| Final reconciliation | 5 |

Correctness is 75 of 100. Latency is scored generously: anything under 5 seconds
at p95 is full marks, and it degrades linearly to zero at 2 minutes. This is not
a speed contest.

**State is worth more than legs, deliberately.** Posting the right legs for an
event is largely mechanical once you have read section 4. Carrying the right
state forward for hours, across a replay, a reversal and a split, is the part
that is hard, and it is what a book of record is for. Within a checkpoint:

| Part of the checkpoint | Share |
| --- | --- |
| Position cost basis | 64% |
| Firm accounts | 11% |
| Wallet cash | 9% |
| Order routing | 8% |
| Cash hold | 5% |
| Position quantity | 2% |
| Trial balance | 1% |

Cost basis dominates because it is the one number here that a balanced,
plausible, confidently wrong implementation still gets wrong. The trial balance
is worth little precisely because almost everyone's balances: it shows your
arithmetic works, not that your accounting does.

**Firm accounts are scored all or nothing.** The revenue, cost and payable
accounts (`2400`, `241x`, `2420`, `2430`, `4xxx`, `5xxx`) are graded as one
block: either your statement of what the firm earned and owes is right, or it
is not. Misclassifying a fee is wrong on every fill rather than on some of
them, and scoring it as a fraction of thirteen accounts would turn being wrong
about your own revenue into a rounding error.

Positions are scored per symbol, so one bad holding costs you one holding.
Reporting a position that should not exist counts against you as well.

**Events are not all worth the same.** About one event in seven correctly
produces no legs at all. Recognising that is worth something, so it scores, but
at a quarter of a normal event. Submitting empty legs for everything is not a
strategy.

---

## 7. Modes

| Mode | Length | Events | Feedback |
| --- | --- | --- | --- |
| `practice` | ~7 min | 800 | **Full.** Every response tells you the correct legs and diffs them against yours. Unlimited reruns |
| `submission` | ~60 min | 4,000 | **Score shown**, no per-event diffs. 3 attempts, each a fresh dataset |
| `final` | ~3 h | 12,000 | Score withheld until submissions close. 1 attempt |

Practice is the executable specification. If anything here is ambiguous, run
against practice and believe what it tells you.

Your stream is generated from a seed unique to you. Two candidates never receive
the same events, so comparing answers with someone else will actively mislead you.

---

## 8. Suggested order of work

1. Consume the stream and print event types. Do not post anything yet.
2. Implement deposits and fees. Watch the trial balance stay at zero.
3. Implement the order lifecycle. Remember that placements and cancellations
   produce no legs, and that the hold covers the charges as well as the
   principal.
4. Implement the fee chain from the tariff: revenue, cost, the regulatory
   payable and the partner share. Get the rounding right before you move on;
   everything downstream inherits it.
5. Implement FIFO cost relief on sells. **This is the largest single source of
   lost marks**, worth more than everything below it combined.
6. Implement checkpoints, including the routes of open orders.
7. Make ingestion idempotent, then reconnect mid-run and confirm nothing
   changes.
8. Implement corporate actions. They look small and are not: an ignored split
   corrupts every position after it.
9. Implement reversals, including the lot-book effect.
10. Implement the four settlement events.
11. Only then worry about batching and latency.

# Ledger Arena: protocol specification

You are building a server that keeps a double-entry book of record. We stream you
a broker's event feed; you post the events into your book and send us back the
journal legs each one produced. We score correctness continuously.

**Your server competes, not you.** The stream is resumable, so a crash at 3am
costs you very little. There is nothing to stay awake for.

> **Clarifications, 2026-08-03** (also announced in Discord; none change scoring):
> 1. Resubmitting an event you already answered now returns
>    `"duplicate": true` instead of re-grading what you sent. Your first
>    submission was always the one scored; the old response was misleading.
> 2. Quantities are now always plain decimal strings. Earlier streams could
>    serialize 10 as `"1E+1"`; if you handled that, your handling still works.
> 3. The mode table in section 7 now matches `/v1/rules`: `final` is 6,000
>    events over ~75 minutes. The table previously said 3 h / 12,000, which
>    was never what the server ran.

---

## 1. What you need

Outbound HTTPS only. You do **not** need a public address, a domain, a
certificate or a cloud account. Your server connects to ours.

Any language. Everything below is plain HTTP and JSON.

| | |
| --- | --- |
| Portal, and where your API key comes from | **https://hiring-arena.twocc.in/ledger** |
| Start the assignment | **https://classroom.github.com/a/gEmUZPq9** |
| What accepting gives you | your own private repository, with the starter kit already in it. Work there and push there: that repo is what we read |
| Deadline, with a live countdown | on the portal |
| Questions | the Discord invite on the portal. **Ask there, not by DM**: anything clarified becomes canon for everyone |

Enter the email your invitation was sent to and the portal issues your key. One
address, one candidate: the key is your identity.

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

Every ledger event carries `offset`, `event_id`, `type` and `payload`, and
nothing else you need. Some also carry `backdated_days`. There is no field that
tells you an event is a duplicate, that it arrived out of order, or that the
difficult part of the run is starting: working that out is the assignment.

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

Periodically the stream delivers a **`checkpoint_request`**. It is not a ledger
event and produces no legs:

```json
{"type": "checkpoint_request",
 "payload": {"checkpoint_id": "cp3", "respond_within_seconds": 60}}
```

Reply within `respond_within_seconds` with your full state. Late answers still
score for correctness but cost you liveness.

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

**As-of queries.** Some checkpoint requests carry an extra field:

```json
{"type": "checkpoint_request",
 "payload": {"checkpoint_id": "asof0", "respond_within_seconds": 60,
             "as_of_event_id": "evt_9f2c11a04b3e7712"}}
```

Answer in exactly the same shape, but describing your book **as it stood once
you had processed that event, in delivery order, and nothing after it**. If a
backdated event arrived later, the as-of answer does not include it. Current
state is not enough to answer these; how you make your history answerable
(replaying an event log, keeping snapshots) is a design decision this
assignment deliberately forces, and it is much easier to take before you
start than after.

### `GET /v1/me?mode=<mode>` and `GET /v1/leaderboard?mode=<mode>`

Your stats and the standings. In `practice` and `submission` `/v1/me` includes
a full breakdown; in `final` it does not.

### `GET /v1/rules`

The scoring weights, live. They are not a secret.

---

## 4. The economics, which your postings must express

This section states what happens commercially. **It does not tell you which
accounts move.** Deriving the journal entries from the economics and the chart
of accounts in section 2 is the assignment; the two worked examples below
anchor the format, and practice mode will tell you whether you are right and
which accounts you disagree on, without telling you the answer.

Two conventions apply everywhere and are graded exactly as stated:

- Every amount is rounded to the cent **independently, half away from zero**.
- Debits equal credits on every transaction, and every leg carries the
  `customer_id` it concerns.

### Cash

**`deposit`** — `customer_id`, `amount`. Cash arrives at the broker; the firm
owes the customer that much more. This one is worked for you:

```
Dr 1100 amount        Cr 2010 amount
```

**`fee_charged`** — `customer_id`, `amount`. The customer pays the firm's fee
out of their wallet; the cash leaves the omnibus account.

**`fee_refund`** — `refunds_source_id`, `customer_id`. Undoes a fee charged
earlier, in full. **The amount is not in this payload**: it is the amount of
the `fee_charged` event being refunded. Refunding the same fee twice is an
error.

**`withdrawal_requested`** — `withdrawal_id`, `customer_id`, `amount`. The
money has left the customer's wallet but has **not yet left the broker**. It
is no longer owed to the customer as wallet money; it is owed to them as a
withdrawal being processed. Those are different obligations.

**`withdrawal_settled`** — `withdrawal_id`. The cash actually leaves. Look the
amount up from the request.

**`withdrawal_rejected`** — `withdrawal_id`. The withdrawal fails and the
money is owed to the customer as wallet money again. No cash moved at any
point.

**`interest_credited`** — `customer_id`, `gross_amount`, `customer_share`.
The broker pays interest on the omnibus balance. The customer is credited
their share; **the firm keeps the remainder as income**. This is not a
pass-through.

**`transfer_between_customers`** — `from_customer_id`, `to_customer_id`,
`amount`. One customer pays another. No external cash moves, and the firm's
total obligation is unchanged: only *whose* money it is changes. A book that
tracks balances per account rather than per (customer, account) will show
nothing happening at all, and will be wrong at every checkpoint afterwards.

### Orders

#### The tariff

Every symbol belongs to one asset class for the whole run: `equity`, `etf` or
`bond`. No broker covers all three, and none is cheapest everywhere.

| Broker | Trades | Brokerage | Custody | Broker cost | Custody cost | Min fee | Ticket |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `BRK-A` | equity, etf | 20 bps | 4 bps | 9 bps | 2 bps | 1.00 | 0.35 |
| `BRK-B` | equity, bond | 15 bps | 5 bps | 8 bps | 3 bps | 2.50 | 3.00 |
| `BRK-C` | etf, bond | 25 bps | 3 bps | 12 bps | 1 bps | 0.50 | 0.20 |

Brokerage and custody are what the **customer** is charged; both are the
firm's revenue. Broker cost and custody cost are what the **firm** is charged
by the executing broker and the custodian for the same trade. All are per
unit of principal. **The brokerage charge is floored at the broker's minimum
fee**, and every fill also costs the firm the broker's flat **ticket** fee
whatever its size.

On top of the tariff, every fill incurs a **regulatory fee of 8 bps of
principal, charged to the customer**. The firm collects it **on the venue's
behalf and owes it onward**: it is not the firm's income, and the firm does
not add to it.

Finally, an introducing **partner is paid a share of what the firm keeps** on
each fill: `partner_rate × (revenue - cost)`, where revenue is what the
customer was charged for brokerage and custody and cost is what the broker
and custodian charged the firm. **Where cost exceeds revenue the share is
zero; there is no clawback.** That is not a corner case: the ticket fee makes
roughly a quarter of all fills loss-making. `partner_rate` may be `0.50`, so
an odd number of cents lands exactly on a half cent; the rounding convention
above decides it, and binary floating point will decide it differently.

Each derived amount (brokerage, custody, regulatory fee, broker cost, custody
cost, partner share) is rounded to the cent independently before use.

#### Routing

**Route to the broker with the lowest total customer charge** (brokerage +
custody) for `quantity × limit_price`, among brokers that trade that asset
class. Ties break on broker id ascending, so there is always exactly one
right answer. You report the route of every still-open order at each
checkpoint; fills name the broker that took them, so open orders are the only
place the routing decision is yours.

#### Placement

**`order_placed`** — `order_id`, `customer_id`, `side`, `symbol`, `quantity`,
`limit_price`, `asset_class`, `est_charges`.

**No money moves and no legs are posted.** A placement creates a *hold*: for
a buy, cash of `quantity × limit_price + est_charges` is no longer spendable;
for a sell, the shares are no longer sellable. Holds are reported at
checkpoints, never posted. `est_charges` is a conservative estimate supplied
in the feed; use it as given.

#### Fills

**`order_partially_filled`** and **`order_filled`** — `order_id`,
`customer_id`, `side`, `symbol`, `quantity`, `price`, `principal`,
`asset_class`, `broker`, `partner_rate`, `trade_id`. An order may fill many
times; `order_filled` is the last fill, closes the order, and releases
whatever remains of the hold.

**The fee amounts are not in the payload.** You are given the broker and the
principal; the tariff turns those into money.

What happens on a **buy**: the customer pays, from their wallet, the
principal plus every charge (brokerage, custody, regulatory fee). The firm
now holds the shares for the customer in omnibus custody, and the customer
has a claim on them. **Cash does not move on the trade date**: the firm owes
the broker the principal until settlement, two days later. The firm's
revenue, its costs, the regulatory fee it collected, and the partner's share
all accrue now, each as what it is. Revenue and cost are booked **gross**;
nothing is netted.

The worked example, for a buy of principal P at a broker whose payable
account is `241x`, with charges b (brokerage), c (custody), r (regulatory),
and costs bc (broker cost), cc (custody cost), ps (partner share):

```
Dr 2010  P + b + c + r          Cr 2350  P
Dr 1200  P                      Cr 2100  P
Dr 5000  bc                     Cr 4000  b
Dr 5010  cc                     Cr 4010  c
Dr 5100  ps                     Cr 2400  r
                                Cr 241x  bc
                                Cr 2420  cc
                                Cr 2430  ps
```

Study why each of those lines is what it is. Every other posting in this
assignment is derived by the same reasoning, and **no other posting is given
to you**.

What happens on a **sell**: the customer's shares are delivered and the sale
proceeds are owed to the firm by the broker until settlement. The customer is
credited the principal **net of** their charges. The custody position and the
customer's claim on it shrink by the **cost** of the shares sold, not their
sale value; the difference is the customer's realised gain or loss, and it is
the *residual* of the legs, never posted directly. The firm's revenue, cost,
regulatory and partner economics are identical to a buy.

**FIFO cost, to the cent, in delivery order.** A lot carries a quantity and a
**total cost**. When a sell consumes part of a lot, the cost relieved is
`round(lot_total × sold_qty / lot_qty)` and the remainder stays with the lot.
Keeping a cost per share and multiplying it out is also FIFO, and it will
disagree with this by a cent, so this formula is the convention graded.

**`trade_settled`** — `trade_id`. Settlement day: the cash from that fill
actually moves, discharging the obligation the fill created. Nothing else
about the trade changes.

**`order_cancelled`**, **`order_rejected`** — `order_id`. **No legs.** The
remaining hold is released.

#### Paying it all onward

Four payables accrue a few cents per trade and are discharged **in full, one
customer at a time**, paid out of omnibus cash. **The amount is never in the
payload**: it is whatever has accumulated on that account for that customer,
so each of these audits every per-trade rounding you have done since the last
one. Settling an account with nothing outstanding is an error.

| Event | Payload | What is paid |
| --- | --- | --- |
| `broker_fees_settled` | `customer_id`, `broker` | that broker's accumulated fees for that customer |
| `custodian_fees_settled` | `customer_id` | the custodian's accumulated fees |
| `reg_fees_remitted` | `customer_id` | the regulatory fees collected |
| `partner_payout` | `customer_id` | the partner's accumulated share |

### Corporate actions

**`dividend_cash`** — `customer_id`, `symbol`, `gross_amount`,
`withholding_tax`, `net_amount`. A dividend arrives. Tax was withheld **at
source**: only the net ever reaches the firm, and the firm owes the tax to
nobody. The net is the customer's money.

**`dividend_reinvested`** — as above plus `reinvest_price`,
`reinvest_quantity`. The broker reinvests the net directly. **Cash is never
involved**: the customer's holding grows by a new lot of `reinvest_quantity`
whose cost is the net amount.

**`stock_split`** — `symbol`, `ratio_from`, `ratio_to`. **No legs.** Quantity
scales by `ratio_to / ratio_from`; the total cost of each lot is unchanged,
so cost per share moves.

**`symbol_change`** — `old_symbol`, `new_symbol`. **No legs.** Re-key the
holding.

### Foreign currency

**`fx_deposit`** — `customer_id`, `amount_foreign`, `currency`,
`market_rate`, `customer_rate`, `usd_at_market_rate`,
`usd_at_customer_rate`.

Money arrives in another currency and is converted. The omnibus account
receives the **market** value. The customer is credited at **their** rate,
which is worse; the gap is the firm's FX spread, earned now. Crediting the
customer with the market figure overstates what they are owed by exactly that
spread.

### Corrections

**`reversal`** — `reverses_event_id`, plus a free-text `reason` you can
ignore. Post the **exact inverse** of the original's legs, and keep both: the
audit trail retains the original and its reversal.

A reversal must also undo the original's effect on your **lot book**, not
just on the accounts. A reversed buy whose lot you leave in place will
balance perfectly and quietly corrupt every subsequent cost basis.


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
| **A systematic defect** | The feed contains **at least one systematic defect**: a class of event that is internally well-formed and wrong. We guarantee its existence and tell you nothing else about it | Your book's invariants are how you find it. Events you identify as the defect are bad data: reject them |

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
| `practice` | ~20 min | 800 | **Diagnostic.** Every response says whether you were right, whether you balanced, and which accounts you disagree on; the worked examples (deposits, buy fills) return their full legs. Checkpoints score every part and name what diverges. 12 runs |
| `submission` | ~60 min | 4,000 | **Score shown**, no per-event feedback. 3 attempts, each a fresh dataset |
| `final` | ~75 min | 6,000 | Score withheld until submissions close. 1 attempt |

The lengths are nominal: your stream is staggered against everyone else's and
drains its tail after the nominal duration, so budget a few extra minutes and
let `stream_end` tell you the run is over, not your own clock. `/v1/rules`
serves these numbers live; if this table and that endpoint ever disagree, the
endpoint wins.

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

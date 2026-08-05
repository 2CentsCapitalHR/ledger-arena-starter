# Ledger Arena: starter kit

You are building a double-entry book of record. We stream you a broker's event
feed; you post the journal legs each event produces and answer state
checkpoints. We score it continuously against a reference implementation.

Every awkward case in here is one that has cost a real back office real money,
and most of them still balanced perfectly while being wrong.

## Start here

**Accept the assignment first:** https://classroom.github.com/a/gEmUZPq9

That creates your own private repository with this kit already in it. Work in
that repository and push to it. **It is what we read**, so a solution kept
anywhere else does not reach us.

If you are reading this on the public template rather than in your own repo,
stop and accept the assignment above.

Then, in your repository:

```bash
git clone <your own repository>
cd <your repository>
pip install -r requirements.txt

python client.py --key ak_your_key_here
```

Get your key from **https://hiring-arena.twocc.in/ledger** by entering the email your
invitation was sent to.

That first run will connect, stream, and score somewhere in the low tens. It is
meant to: `book.py` implements one event type as a worked example and raises on
the rest. Seeing the whole loop work before you have written a line means any
later failure is yours and not ours.

It does not score zero because roughly one event in seven correctly produces no
legs at all, and submitting nothing for those is the right answer. Treat the
number you get on that first run as the floor, not as progress.

It ends by printing what it could not post, which is your to-do list:

```
not implemented yet (1174 events skipped):
  order_filled                     287 events
  trade_settled                    281 events
  ...
```

Then read **`PROTOCOL.md`**. It is the entire specification: the accounts, the
broker tariff, all twenty-three event types, every posting rule, and how the
scoring works.

## What is already done for you

`client.py` is finished. It subscribes, survives the deliberate mid-run replay,
resumes from an offset, batches postings, and answers checkpoints on time. That
is transport, and it is not what we are assessing.

`book.py` is where you work. It hands you one event and takes back its legs.

## Two things to get right before anything else

**Use `Decimal`, never `float`.** Money here does not always divide evenly. A
float implementation will disagree with us by a cent in places that are very
hard to find afterwards.

**Key balances by `(customer, account)`, not by account.** At least one event
moves money between two customers on the same account. An account-level book
shows nothing wrong at all, and its trial balance agrees with it.

**The firm has its own money.** Brokerage and custody are revenue, the executing
broker and the custodian cost us, the regulatory fee is collected for the venue,
and an introducing partner takes a share of what is left. Those accounts are
graded as one block: your statement of what the firm earned and owes either ties
or it does not.

## How long this takes

**Budget 12 to 18 hours**, more if double-entry bookkeeping is new to you. The
transport is already written, so all of that is the ledger itself.

If you run out of time, cut the four settlement events first (worth about 8
points), then reversals (another 10), and only then corporate actions, which
are worth far more than they look: a split you ignore corrupts every position
after it. `PROTOCOL.md` has the measured table.

Stopping early and writing down what is missing costs you nothing and reads
better than something half-built.

## Tiers

| Tier | Attempts | Score | What it is for |
| --- | --- | --- | --- |
| `practice` | 15 | shown, with diagnostics on every event | develop here |
| `submission` | 3 | shown | scored; tuning against it is expected |
| `final` | 1 | withheld | this is what ranks you |

**`/v1/rules` is the authority on these numbers.** If this table and that
endpoint ever disagree, the endpoint wins: check it before you plan around a
figure here.

Practice tells you, on every event, whether you were right, whether your legs
balanced, and which accounts you disagree on. Use it deliberately rather than
as a compiler: fifteen runs is plenty for an honest debugging loop, but it is
not infinite, and each one costs twenty minutes of wall clock.

Each attempt draws a fresh dataset, so a retry is a new problem rather than a
retake of one you have already seen scored.

Each attempt draws a fresh dataset, so a retry is a new problem rather than a
retake of one you have already seen scored.

## Rules

- **One address, one candidate.** Your key is your identity.
- **Use AI tools if you normally do.** We do. There is no penalty and no
  detection game. But you will walk us through the code in a live session and
  change it while we watch, so be able to defend every line of it.
- **Ask in Discord, not by DM.** Anything clarified there becomes canon for
  everyone, which is fairer than rewarding whoever thought to ask privately.
- **If you run out of time, stop and write down what is missing** and how you
  would have done it. That costs you nothing and reads far better than
  something half-built and unexplained.

## Things the stream will do to you

All deliberate, all in `PROTOCOL.md`, none of them bugs: duplicate delivery, a
forced disconnect that rewinds you several hundred events, fills that arrive
before their placement, oversells, reversals of events you never received, and
payloads that will not parse.

A server that rejects one bad event and keeps consuming beats one that stops.

## Running a graded tier

```bash
python client.py --key ak_... --mode submission
```

It will ask you to confirm, because attempts are limited. A run that cannot
finish before the deadline is refused rather than started, so you will not lose
an attempt to the clock.

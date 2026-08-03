"""Your ledger. This is the whole assignment.

`client.py` handles the network and hands you one event at a time. You return
the journal legs it produced. Some events correctly produce none: return an
empty list, not None-as-an-accident.

One event type is implemented as a worked example. The rest raise, with the rule
from PROTOCOL.md quoted in the message, so a practice run tells you exactly what
is left rather than silently scoring zero.

Two things to get right before anything else:

  * Use `Decimal`, never `float`. Money here does not always divide evenly, and
    a float implementation will disagree with us by a cent in places you will
    struggle to find.
  * Key balances by (customer, account), not by account. At least one event
    moves money between two customers on the same account, and an
    account-level book shows nothing wrong at all.
  * The firm has its own money. Brokerage and custody are revenue, the
    executing broker and the custodian cost us, the regulatory fee is
    collected for the venue, and an introducing partner is paid a share of
    what is left. Those are scored as one block: your statement of what the
    firm earned and owes either ties or it does not.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
ZERO = D("0.00")


def money(x: Decimal) -> Decimal:
    """2 decimal places, half away from zero. Not round(), which is half-even."""
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def leg(account: str, customer_id: str, debit=ZERO, credit=ZERO) -> dict:
    return {"account": account, "customer_id": customer_id,
            "debit": str(money(D(debit))), "credit": str(money(D(credit)))}


class Book:
    def __init__(self) -> None:
        # balances[(customer_id, account)] = debit-positive balance
        self.balances: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
        self.seen: set[str] = set()
        # What you have not written yet. An unimplemented handler must not stop
        # the run: the client keeps consuming and tells you the list at the end.
        self.todo: dict[str, int] = defaultdict(int)

    # -----------------------------------------------------------------------
    def apply(self, ev: dict) -> list[dict]:
        """Post one event and return its legs.

        The same event_id can arrive more than once, and the server will
        deliberately re-send several hundred events partway through the run.
        Posting twice is the single most expensive mistake available here.
        """
        eid = ev["event_id"]
        if eid in self.seen:
            return []                      # already posted; nothing new happens
        self.seen.add(eid)

        handler = getattr(self, "on_" + ev["type"], None)
        if handler is None:
            self.todo[ev["type"]] += 1
            return []
        try:
            legs = handler(ev["payload"], ev) or []
        except NotImplementedError:
            # Not written yet. Submit nothing for it and carry on, so one
            # missing handler costs you that event rather than the whole run.
            self.todo[ev["type"]] += 1
            return []
        except Rejected:
            # An event you refuse still gets a submission, with no legs, and it
            # must leave your book exactly as it was.
            return []
        self._post(legs)
        return legs

    def _post(self, legs: list[dict]) -> None:
        dr = sum(D(l["debit"]) for l in legs)
        cr = sum(D(l["credit"]) for l in legs)
        if money(dr) != money(cr):
            raise AssertionError(f"unbalanced: dr {dr} cr {cr}")
        for l in legs:
            self.balances[(l["customer_id"], l["account"])] += (
                D(l["debit"]) - D(l["credit"]))

    # -- worked example -----------------------------------------------------
    def on_deposit(self, p: dict, ev: dict) -> list[dict]:
        """Cash arrives, and the firm owes the customer more.

            Dr 1100 amount        Cr 2010 amount
        """
        amount = money(D(p["amount"]))
        cid = p["customer_id"]
        return [leg("1100", cid, debit=amount),
                leg("2010", cid, credit=amount)]

    # -- yours --------------------------------------------------------------
    def on_fee_charged(self, p, ev):
        raise NotImplementedError(
            "The customer pays the firm's fee from their wallet; the cash "
            "leaves the omnibus account")

    def on_fee_refund(self, p, ev):
        raise NotImplementedError(
            "Undoes a fee in full. The amount is NOT in this payload: it "
            "is the amount of the fee_charged event named by "
            "refunds_source_id. Refunding twice is an error")

    def on_interest_credited(self, p, ev):
        raise NotImplementedError(
            "The customer is credited customer_share; the firm keeps the "
            "remainder of gross_amount as income. Not a pass-through")

    def on_transfer_between_customers(self, p, ev):
        raise NotImplementedError(
            "One customer pays another. No external cash moves; only "
            "WHOSE money it is changes. A per-account book shows nothing "
            "at all")

    def on_fx_deposit(self, p, ev):
        raise NotImplementedError(
            "The omnibus account receives the market value; the customer "
            "is credited at THEIR rate; the gap is the firm's FX spread, "
            "earned now")

    def on_withdrawal_requested(self, p, ev):
        raise NotImplementedError(
            "The money left the wallet but not the broker: it is owed as "
            "a withdrawal in processing, a different obligation from "
            "wallet money")

    def on_withdrawal_settled(self, p, ev):
        raise NotImplementedError(
            "The cash actually leaves. Look the amount up from the "
            "request")

    def on_withdrawal_rejected(self, p, ev):
        raise NotImplementedError(
            "The withdrawal fails; the money is wallet money again. No "
            "cash ever moved")

    def on_order_placed(self, p, ev):
        raise NotImplementedError(
            "No legs. A placement moves no money: it creates a hold of "
            "quantity * limit_price + est_charges, reported at "
            "checkpoints and never posted")

    def on_order_partially_filled(self, p, ev):
        return self.on_order_filled(p, ev)

    def on_order_filled(self, p, ev):
        raise NotImplementedError(
            "The fee amounts are NOT in the payload: derive them from the "
            "tariff in PROTOCOL.md section 4, each rounded to the cent "
            "independently. A buy is fully worked in section 4; study why "
            "each leg is what it is, because the sell and everything else "
            "must be derived by the same reasoning. Cash does NOT move on "
            "the trade date")

    # -- what the firm earns and owes ---------------------------------------
    def on_broker_fees_settled(self, p, ev):
        raise NotImplementedError(
            "Pay that broker's WHOLE accumulated payable for that "
            "customer from omnibus cash. The amount is not in the "
            "payload: it is every cent accrued since the last settlement")

    def on_custodian_fees_settled(self, p, ev):
        raise NotImplementedError(
            "As broker fees, for the custodian's accumulated payable")

    def on_reg_fees_remitted(self, p, ev):
        raise NotImplementedError(
            "As broker fees, for the regulatory fees collected on the "
            "venue's behalf")

    def on_partner_payout(self, p, ev):
        raise NotImplementedError(
            "As broker fees, for the partner's accumulated share")

    def on_trade_settled(self, p, ev):
        raise NotImplementedError(
            "Settlement day: the cash from that fill actually moves, "
            "discharging the obligation the fill created")

    def on_order_cancelled(self, p, ev):
        raise NotImplementedError(
            "No legs. Release the remaining hold")

    def on_order_rejected(self, p, ev):
        return self.on_order_cancelled(p, ev)

    def on_dividend_cash(self, p, ev):
        raise NotImplementedError(
            "Only the net ever reaches the firm; tax was withheld at "
            "source and is owed to nobody. The net is the customer's "
            "money")

    def on_dividend_reinvested(self, p, ev):
        raise NotImplementedError(
            "The broker reinvests the net directly: cash is never "
            "involved, and the holding grows by a new lot costing the net "
            "amount")

    def on_stock_split(self, p, ev):
        raise NotImplementedError(
            "No legs. Quantity scales by ratio_to/ratio_from; each lot's "
            "total cost does not change")

    def on_symbol_change(self, p, ev):
        raise NotImplementedError(
            "No legs. Re-key the holding")

    def on_reversal(self, p, ev):
        raise NotImplementedError(
            "Post the exact inverse of the original's legs, and undo its "
            "effect on your LOT BOOK too. A reversed buy whose lot you "
            "leave behind balances perfectly and corrupts every later "
            "cost basis")

    # -- reporting ----------------------------------------------------------
    def snapshot(self) -> dict:
        """What a checkpoint_request wants: your whole state, right now.

        Report every account you have ever posted to, including any that have
        netted back to zero. Trial balance values are debit-positive, so
        liabilities carry a negative sign.
        """
        tb: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for (_cid, acct), bal in self.balances.items():
            tb[acct] += bal

        customers: dict[str, dict] = {}
        for (cid, acct), bal in self.balances.items():
            c = customers.setdefault(cid, {"wallet_cash": ZERO,
                                           "cash_hold": ZERO, "positions": {}})
            if acct == "2010":
                c["wallet_cash"] += -bal          # a liability, so credit-positive

        return {
            # Every order you believe is still open, mapped to the broker the
            # routing rule sends it to. Fills name the broker, so open orders
            # are the only place the decision is actually yours.
            "open_order_routes": {},
            "trial_balance": {a: str(money(v)) for a, v in sorted(tb.items())},
            "customers": {cid: {"wallet_cash": str(money(c["wallet_cash"])),
                                "cash_hold": str(money(c["cash_hold"])),
                                "positions": c["positions"]}
                          for cid, c in sorted(customers.items())},
        }


class Rejected(Exception):
    """Raise from a handler for an event you refuse to post.

    An oversell, a reversal of something you never received, a payload that
    will not parse. Rejecting one event and carrying on beats stopping: a
    server that stalls misses everything after it.
    """

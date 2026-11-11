"""One deterministic execution path for human and automatic approvals. No model use."""

import asyncio
from decimal import Decimal
import json
from uuid import uuid4

from platform_app.storage import now

from .bands import assign_band
from .compliance import validate_price
from .repository import encode
from .stability import analyze_stability
from .transport import CommerceWriter


def automatic_allowed(mode, band):
    return mode in {"assisted", "autonomous"} and band == "auto_approve" or mode == "autonomous" and band == "review"


class Dispatcher:
    def __init__(self, repository, commerce, fence):
        self.repo, self.store, self.commerce = repository, repository.store, commerce
        self.fence, self.writer = fence, CommerceWriter(commerce)

    def _receipt(self, db, batch_key, receipt):
        row = db.execute("SELECT item_refs FROM price_outbox WHERE batch_key=?", (batch_key,)).fetchone()
        refs = {item["sku"]: item for item in json.loads(row["item_refs"])}
        for outcome in receipt["items"]:
            ref = refs[outcome["sku"]]
            item = self.repo.read(db, ref["id"])
            if item["revision"] != ref["revision"]:
                continue
            execution = {**outcome, "batch_key": batch_key}
            unchanged = (outcome["status"] == "applied"
                         and Decimal(outcome["prior_price"]) == Decimal(outcome["new_price"]))
            execution["unchanged"] = unchanged
            status = "unchanged" if unchanged else "applied" if outcome["status"] == "applied" else "execution_rejected"
            self.repo.state(db, item["id"], status, item["approval"], execution=execution)
            self.store._audit(db, "system", "price_receipt", item["run_id"],
                              {"item_id": item["id"], "revision": item["revision"], **execution})
        db.execute("UPDATE price_outbox SET status='resolved',receipt=? WHERE batch_key=?", (encode(receipt), batch_key))

    def _run_allows_dispatch(self, item):
        if item.get("reverts_item_id"):
            origin = self.repo.get(item["reverts_item_id"])
            receipt = (origin or {}).get("execution") or {}
            approval = item.get("approval") or {}
            # A newly calculated, explicitly human compensating change is
            # independent of whether another item failed in its originating run.
            # The API never accepts these immutable linkage fields from a caller.
            return bool(origin and origin["status"] == "applied" and receipt.get("status") == "applied"
                        and not receipt.get("unchanged") and approval.get("kind") == "human"
                        and approval.get("reason") and item["sku"] == origin["sku"]
                        and item["price_version"] == receipt.get("new_version")
                        and Decimal(item["current_price"]) == Decimal(receipt["new_price"])
                        and Decimal(item["proposed_price"]) == Decimal(receipt["prior_price"])
                        and item.get("reverts_batch_key") == receipt.get("batch_key"))
        run = self.store.get_run(item["run_id"])
        # Standalone deterministic-domain fixtures have no graph run. Runtime
        # recommendations are created only by the grounded graph's Validation node.
        if run is None:
            return True
        return (run["request"].get("kind") == "grounded"
                and (run["status"] in {"awaiting_review", "completed"}
                     or run["status"] == "running" and run["stage"] == "execution"))

    async def reconcile(self):
        """Read receipts only. Recovery never resubmits an old automatic intent."""
        receipts = []
        async with self.fence:
            with self.store.connection() as db:
                rows = db.execute("SELECT * FROM price_outbox WHERE status IN ('sent','unknown')").fetchall()
            for row in rows:
                receipt = await self.writer.lookup(json.loads(row["payload"]))
                if receipt:
                    with self.store.connection() as db:
                        self._receipt(db, row["batch_key"], receipt)
                    receipts.append(receipt)
        return receipts

    async def dispatch_due(self, item_ids=None):
        receipts = await self.reconcile()
        # This lock also guards mode/kill, approval, and the socket handoff. Kill
        # acknowledgement occurs after any admitted send has returned or timed out.
        async with self.fence:
            with self.store.connection() as db:
                state, policy = self.repo.control(db)
                rows = self.repo.queue(status="approved") + self.repo.queue(status="hold")
                for item in rows:
                    if item["status"] in {"approved", "hold"} and not self._run_allows_dispatch(item):
                        self.repo.state(db, item["id"], "canceled")
                        self.store._audit(db, "system", "run_dispatch_fenced", item["run_id"],
                                          {"item_id": item["id"], "reason": "The run is not in an executable grounded state."})
                        continue
                    if item["status"] == "hold" and item["hold_until"] <= now():
                        if state["mode"] == "autonomous" and item["mode_version"] == state["version"]:
                            approval = {"kind": "automatic", "actor": "system", "reason": "Autonomous hold expired",
                                        "mode_version": state["version"], "approved_at": now()}
                            self.repo.state(db, item["id"], "approved", approval)
                            self.store._audit(db, "system", "hold_released", item["run_id"], {"item_id": item["id"]})
                        else:
                            self.repo.state(db, item["id"], "canceled")
            rows = self.repo.queue(status="approved")
            if item_ids is not None:
                wanted = set(item_ids)
                rows = [item for item in rows if item["id"] in wanted]
            if not rows:
                return receipts
            catalog, history = await asyncio.gather(self.commerce.all("/catalog"), self.commerce.all("/price-history"))
            products = {product["sku"]: product for product in catalog["items"]}
            # Separate actors in batch receipts. Re-check every group against the
            # actual current family ladder, rather than a partially approved plan.
            for kind in ("human", "automatic"):
                group = [item for item in rows if item["approval"] and item["approval"]["kind"] == kind]
                seen = set()
                group = [item for item in group if not (item["sku"] in seen or seen.add(item["sku"]))]
                with self.store.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    state, policy = self.repo.control(db)
                    changes = {item["sku"]: item["proposed_price"] for item in group}
                    ready = []
                    for old in group:
                        item = self.repo.read(db, old["id"])
                        product = products.get(item["sku"])
                        compliance = validate_price(product, item["proposed_price"], catalog["items"],
                                                    changes=changes, expected_version=item["price_version"], policy=policy,
                                                    constraints=item.get("run_constraints"))
                        stability = analyze_stability(product, item["proposed_price"], history["items"],
                                                      catalog["items"], policy) if product else {"cooldown_active": False}
                        for signal in ("oscillation", "damping_applied", "novel_market"):
                            stability[signal] = bool(stability.get(signal) or item.get("stability", {}).get(signal))
                        risk = assign_band(item, product, compliance, stability, policy) if product else {"band": "escalate"}
                        approval = item.get("approval")
                        authorized = (item["status"] == "approved" and approval
                                      and self._run_allows_dispatch(item)
                                      and approval["mode_version"] == state["version"]
                                      and (kind == "human" and (risk["band"] != "escalate" or approval.get("reason"))
                                           or kind == "automatic" and automatic_allowed(state["mode"], risk["band"]))
                                      and item.get("forecast") is not None)
                        if compliance["status"] != "passed" or stability["cooldown_active"] or not authorized:
                            stale_source = any(r["rule"] == "source_price_version" and not r["passed"]
                                               for r in compliance["rules"])
                            status = ("stale" if stale_source else "blocked" if compliance["status"] != "passed"
                                      or stability["cooldown_active"] else "stale")
                            self.repo.state(db, item["id"], status)
                            self.store._audit(db, "system", "dispatch_veto", item["run_id"],
                                              {"item_id": item["id"], "compliance": compliance,
                                               "cooldown": stability["cooldown_active"], "authorized": bool(authorized)})
                        else:
                            ready.append(item)
                    # Dropping an item can invalidate another member's ladder.
                    changes = {item["sku"]: item["proposed_price"] for item in ready}
                    final = []
                    for item in ready:
                        result = validate_price(products[item["sku"]], item["proposed_price"], catalog["items"],
                                                changes=changes, expected_version=item["price_version"], policy=policy,
                                                constraints=item.get("run_constraints"))
                        if result["status"] == "passed":
                            final.append(item)
                        else:
                            self.repo.state(db, item["id"], "blocked")
                            self.store._audit(db, "system", "dispatch_ladder_veto", item["run_id"],
                                              {"item_id": item["id"], "compliance": result})
                    if not final:
                        continue
                    batch_key = "platform-" + str(uuid4())
                    payload = {"batch_key": batch_key, "actor": "system" if kind == "automatic" else "local-operator",
                               "approval_kind": kind, "items": [{"sku": item["sku"], "price": item["proposed_price"],
                                                                 "expected_version": item["price_version"]} for item in final]}
                    refs = [{"id": item["id"], "revision": item["revision"], "sku": item["sku"]} for item in final]
                    db.execute("INSERT INTO price_outbox VALUES(?,?,?,?,?,'sent',NULL,0)",
                               (batch_key, now(), state["version"], encode(payload), encode(refs)))
                    for item in final:
                        self.repo.state(db, item["id"], "dispatching", item["approval"])
                        self.store._audit(db, "system", "price_dispatch", item["run_id"],
                                          {"item_id": item["id"], "batch_key": batch_key,
                                           "mode": state["mode"], "generation": state["version"], "kind": kind})
                def on_attempt(attempt):
                    with self.store.connection() as attempt_db:
                        attempt_db.execute("UPDATE price_outbox SET attempts=? WHERE batch_key=?", (attempt, batch_key))
                        self.store._audit(attempt_db, "system", "price_http_attempt", None,
                                          {"batch_key": batch_key, "attempt": attempt})

                try:
                    receipt = await self.writer.send(payload, on_attempt)
                except asyncio.CancelledError:
                    with self.store.connection() as db:
                        db.execute("UPDATE price_outbox SET status='unknown' WHERE batch_key=?", (batch_key,))
                        for item in final:
                            self.repo.state(db, item["id"], "unknown", item["approval"], execution={
                                "batch_key": batch_key, "status": "unknown", "sku": item["sku"],
                                "prior_price": item["current_price"], "new_price": item["proposed_price"],
                                "prior_version": item["price_version"], "new_version": None, "applied_at": None})
                            self.store._audit(db, "system", "price_dispatch_interrupted", item["run_id"],
                                              {"item_id": item["id"], "batch_key": batch_key})
                    raise
                with self.store.connection() as db:
                    if receipt:
                        self._receipt(db, batch_key, receipt)
                        receipts.append(receipt)
                    else:
                        db.execute("UPDATE price_outbox SET status='unknown' WHERE batch_key=?", (batch_key,))
                        for item in final:
                            execution = {"batch_key": batch_key, "status": "unknown", "sku": item["sku"],
                                         "prior_price": item["current_price"], "new_price": item["proposed_price"],
                                         "prior_version": item["price_version"], "new_version": None, "applied_at": None}
                            self.repo.state(db, item["id"], "unknown", item["approval"], execution=execution)
                            self.store._audit(db, "system", "price_result_unknown", item["run_id"], execution)
                # A second actor group must re-read after the first group's writes.
                catalog = await self.commerce.all("/catalog")
                products = {product["sku"]: product for product in catalog["items"]}
        return receipts

"""Atomic policy/mode generations and kill fencing."""

from .models import GovernancePolicy, ModeUpdate
from .repository import encode


async def set_mode(service, mode, hold_seconds=None):
    update = ModeUpdate(mode=mode, hold_seconds=hold_seconds)
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior, policy = service.repo.control(db)
            if update.mode == prior["mode"] and (hold_seconds is None or hold_seconds == policy.hold_seconds):
                return prior
            if hold_seconds is not None:
                policy = policy.model_copy(update={"hold_seconds": hold_seconds})
            canceled = service.repo.cancel_pending(db, automatic_only=False)
            db.execute("UPDATE governance_control SET mode=?,generation=generation+1,policy=? WHERE singleton=1",
                       (update.mode, encode(policy.model_dump())))
            state = service.repo.control(db)[0]
            service.store._audit(db, "human", "mode_changed", None,
                                {"prior": prior, "current": state, "canceled": canceled})
    return {**state, "canceled": canceled}


async def kill(service):
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior, _ = service.repo.control(db)
            canceled = service.repo.cancel_pending(db, automatic_only=False)
            db.execute("UPDATE governance_control SET mode='supervised',generation=generation+1 WHERE singleton=1")
            state = service.repo.control(db)[0]
            in_flight = db.execute("SELECT batch_key,status FROM price_outbox WHERE status IN ('sent','unknown')").fetchall()
            service.store._audit(db, "human", "kill_switch", None,
                                {"prior": prior, "current": state, "canceled": canceled,
                                 "reconciliation": [dict(row) for row in in_flight]})
    return {**state, "canceled": canceled,
            "reconciliation": [dict(row) for row in in_flight]}


async def update_policy(service, changes):
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            prior, policy = service.repo.control(db)
            changes = changes.model_dump(exclude_unset=True) if isinstance(changes, GovernancePolicy) else changes
            policy = GovernancePolicy.model_validate({**policy.model_dump(), **changes})
            canceled = service.repo.cancel_pending(db, automatic_only=False)
            db.execute("UPDATE governance_control SET generation=generation+1,policy_version=policy_version+1,policy=? "
                       "WHERE singleton=1", (encode(policy.model_dump()),))
            state = service.repo.control(db)[0]
            service.store._audit(db, "human", "governance_policy_changed", None,
                                {"prior_version": prior["policy_version"], "version": state["policy_version"],
                                 "changed_fields": sorted(changes), "thresholds": policy.model_dump(), "canceled": canceled})
    return service.repo.policy()


async def cancel_run(service, run_id, reason="run_failed"):
    """Revoke unsent run work without pretending to recall admitted HTTP writes."""
    async with service.fence:
        with service.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute("SELECT s.id FROM recommendation_state s JOIN recommendations r "
                              "ON r.id=s.id AND r.revision=s.revision WHERE r.run_id=? "
                              "AND s.status IN ('approved','hold','dispatching')", (run_id,)).fetchall()
            canceled = []
            for row in rows:
                sent = db.execute("SELECT 1 FROM price_outbox WHERE status IN ('sent','unknown') "
                                  "AND item_refs LIKE ?", (f'%"id":"{row["id"]}"%',)).fetchone()
                if not sent:
                    service.repo.state(db, row["id"], "canceled")
                    canceled.append(row["id"])
            service.store._audit(db, "system", "run_authorizations_canceled", run_id,
                                {"item_ids": canceled, "reason": service.redact(reason)})
    return {"run_id": run_id, "canceled": len(canceled), "item_ids": canceled}

"""Scoped immutable decision evidence and mutable workflow state in app.db."""

from platform_app.database import sql

import json
import hashlib
from uuid import uuid4

from platform_app.storage import Store, now

from .models import GovernancePolicy


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def revision_hash(item):
    """Bind a human revision to its newly calculated numerical artifact."""
    keys = ("sku", "current_price", "proposed_price", "price_version", "forecast", "current_forecast",
            "impact", "elasticity", "confidence", "configuration", "run_constraints", "policy_version",
            "optimal_price_uncertainty")
    return hashlib.sha256(encode({key: item.get(key) for key in keys}).encode()).hexdigest()


class Repository:
    def __init__(self, store: Store):
        self.store = store
        with store.connection() as db:
            db.executescript(sql("governance_ddl.sql"))
            db.executescript(sql("governance_dml.sql"))
            # A fresh application never revives a prior automatic authorization.
            prior = dict(db.execute("SELECT * FROM governance_control WHERE singleton=1").fetchone())
            db.execute("UPDATE governance_control SET mode='supervised',generation=generation+1 WHERE singleton=1")
            canceled = self.cancel_pending(db, automatic_only=False)
            if prior["mode"] != "supervised" or canceled:
                store._audit(db, "system", "governance_boot_fence", None,
                             {"prior_mode": prior["mode"], "canceled": canceled})

    @staticmethod
    def control(db):
        row = dict(db.execute("SELECT * FROM governance_control WHERE singleton=1").fetchone())
        policy = GovernancePolicy.model_validate_json(row["policy"])
        return {"mode": row["mode"], "version": row["generation"], "generation": row["generation"],
                "policy_version": row["policy_version"], "hold_seconds": policy.hold_seconds}, policy

    def mode(self):
        with self.store.connection() as db:
            return self.control(db)[0]

    def policy(self):
        with self.store.connection() as db:
            state, policy = self.control(db)
            return {"version": state["policy_version"], "thresholds": policy.model_dump(),
                    "calibration": "initial demo defaults; operator configured, not empirically guaranteed"}

    @staticmethod
    def read(db, item_id):
        row = db.execute("SELECT r.evidence,s.* FROM recommendation_state s JOIN recommendations r "
                         "ON r.id=s.id AND r.revision=s.revision WHERE s.id=?", (item_id,)).fetchone()
        if row is None:
            return None
        item = json.loads(row["evidence"])
        return {**item, "id": row["id"], "revision": row["revision"], "status": row["status"],
                "executable": row["status"] == "approved" and item.get("compliance_status") == "passed"
                              and bool(row["approval"]) and item.get("forecast") is not None,
                "approval": json.loads(row["approval"]) if row["approval"] else None,
                "hold_until": row["hold_until"],
                "execution": json.loads(row["execution"]) if row["execution"] else None}

    def get(self, item_id):
        with self.store.connection() as db:
            return self.read(db, item_id)

    def queue(self, run_id=None, status=None, band=None, automatic=None, limit=5000):
        predicates, params = [], []
        for value, expression in ((run_id, "r.run_id=?"), (status, "s.status=?"),
                                  (band, "json_extract(r.evidence,'$.band')=?")):
            if value is not None:
                predicates.append(expression)
                params.append(value)
        if automatic is not None:
            predicates.append("COALESCE(json_extract(s.approval,'$.kind'),'') "
                              + ("=" if automatic else "!=") + " ?")
            params.append("automatic")
        where = " WHERE " + " AND ".join(predicates) if predicates else ""
        with self.store.connection() as db:
            ids = db.execute("SELECT s.id FROM recommendation_state s JOIN recommendations r "
                             "ON r.id=s.id AND r.revision=s.revision" + where +
                             " ORDER BY r.created_at DESC,r.sku LIMIT ?", (*params, limit)).fetchall()
            return [self.read(db, row["id"]) for row in ids]

    @staticmethod
    def insert(db, item, status, approval=None, hold_until=None):
        item = {**item, "id": item.get("id", str(uuid4())), "revision": item.get("revision", 1)}
        item = {key: value for key, value in item.items() if key not in {"status", "approval", "hold_until", "execution"}}
        db.execute("INSERT INTO recommendations VALUES(?,?,?,?,?,?)",
                   (item["id"], item["revision"], item["run_id"], item["sku"], now(), encode(item)))
        db.execute("INSERT INTO recommendation_state VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                   "revision=excluded.revision,status=excluded.status,approval=excluded.approval,"
                   "hold_until=excluded.hold_until,execution=NULL",
                   (item["id"], item["revision"], status, encode(approval) if approval else None, hold_until, None))
        return item["id"]

    @staticmethod
    def state(db, item_id, status, approval=None, hold_until=None, execution=None):
        db.execute("UPDATE recommendation_state SET status=?,approval=?,hold_until=?,execution=? WHERE id=?",
                   (status, encode(approval) if approval else None, hold_until,
                    encode(execution) if execution else None, item_id))

    @staticmethod
    def cancel_pending(db, automatic_only=True):
        rows = db.execute("SELECT id,status,approval FROM recommendation_state "
                          "WHERE status IN ('approved','hold','dispatching')").fetchall()
        count = 0
        for row in rows:
            approval = json.loads(row["approval"]) if row["approval"] else None
            if not automatic_only or row["status"] == "hold" or (approval and approval["kind"] == "automatic"):
                # Already-sent work is reconciled, never described as recalled.
                sent = db.execute("SELECT 1 FROM price_outbox WHERE status IN ('sent','unknown') "
                                  "AND item_refs LIKE ?", (f'%"id":"{row["id"]}"%',)).fetchone()
                if not sent:
                    Repository.state(db, row["id"], "canceled")
                    count += 1
        db.execute("UPDATE price_outbox SET status='canceled' WHERE status='prepared'")
        return count

    def history(self, item_id):
        with self.store.connection() as db:
            rows = db.execute("SELECT revision,created_at,evidence FROM recommendations WHERE id=? ORDER BY revision",
                              (item_id,)).fetchall()
            return [{"revision": row["revision"], "created_at": row["created_at"],
                     "evidence": json.loads(row["evidence"])} for row in rows]

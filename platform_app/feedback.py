"""HTTP readback of mature, disjoint post-push windows and bounded model learning."""

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math

from platform_app.storage import now


class Feedback:
    def __init__(self, store, commerce):
        self.store, self.commerce = store, commerce
        with store.connection() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS realized_outcomes(
                item_id TEXT PRIMARY KEY, sku TEXT NOT NULL, run_id TEXT NOT NULL,
                status TEXT NOT NULL, result TEXT NOT NULL, updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS learning_versions(
                sku TEXT NOT NULL, version INTEGER NOT NULL, source_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL, state TEXT NOT NULL,
                PRIMARY KEY(sku,version));
              CREATE TRIGGER IF NOT EXISTS learning_no_update BEFORE UPDATE ON learning_versions
                BEGIN SELECT RAISE(ABORT,'Learning versions are immutable'); END;
              CREATE TRIGGER IF NOT EXISTS learning_no_delete BEFORE DELETE ON learning_versions
                BEGIN SELECT RAISE(ABORT,'Learning versions are immutable'); END;
              CREATE TABLE IF NOT EXISTS observed_days(
                sku TEXT NOT NULL, day TEXT NOT NULL, item_id TEXT NOT NULL,
                PRIMARY KEY(sku,day));
            """)

    def states(self):
        with self.store.connection() as db:
            rows = db.execute("SELECT l.* FROM learning_versions l JOIN (SELECT sku,MAX(version) v "
                              "FROM learning_versions GROUP BY sku) x ON l.sku=x.sku AND l.version=x.v").fetchall()
            return {r["sku"]: json.loads(r["state"]) for r in rows}

    def outcomes(self):
        with self.store.connection() as db:
            rows = db.execute("SELECT * FROM realized_outcomes ORDER BY updated_at DESC").fetchall()
            return [{**dict(row), "result": json.loads(row["result"])} for row in rows]

    async def refresh(self, items, *, today: date | None = None):
        today = today or datetime.now(timezone.utc).date()
        applied = [i for i in items if i.get("status") != "unchanged" and not (i.get("execution") or {}).get("unchanged")
                   and (i.get("status") in {"applied", "pushed"}
                        or (i.get("execution") or {}).get("status") == "applied")]
        for item in applied:
            with self.store.connection() as db:
                old = db.execute("SELECT status FROM realized_outcomes WHERE item_id=?", (item["id"],)).fetchone()
            if old and old["status"] in {"observed", "excluded"}:
                continue
            run = self.store.get_run(item["run_id"])
            horizon = (run or {}).get("request", {}).get("horizon_days", 14)
            execution = item.get("execution") or {}
            timestamp = execution.get("applied_at") or execution.get("pushed_at") or item.get("applied_at")
            if not timestamp:
                self._save(item, "pending", {"reason": "Commerce receipt has no confirmed application timestamp."})
                continue
            start = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).date() + timedelta(days=1)
            end = start + timedelta(days=horizon)
            window = {"start": start.isoformat(), "end_exclusive": end.isoformat(), "horizon_days": horizon,
                      "source": "Commerce /sales over HTTP", "cost_basis": "cost in decision evidence; no realized cost feed"}
            if today < end:
                self._save(item, "pending", {**window, "reason": "The complete post-change observation window has not elapsed."})
                continue
            response = await self.commerce.all("/sales", sku=item["sku"], since=start.isoformat())
            rows = [r for r in response["items"] if start <= date.fromisoformat(r["date"][:10]) < end]
            days = {r["date"][:10] for r in rows}
            if len(rows) != horizon or len(days) != horizon:
                self._save(item, "pending", {**window, "observed_days": len(days),
                                           "reason": "Sales are incomplete; absence is not treated as zero sales."})
                continue
            if any(abs(float(r["price"]) - float(item["proposed_price"])) > .005 for r in rows):
                self._save(item, "excluded", {**window, "reason": "An intervening price changed the forecast treatment."})
                continue
            forecast = item.get("forecast")
            if not forecast:
                self._save(item, "excluded", {**window, "reason": "The approved revision has no aligned forecast."})
                continue
            units = sum(r["units"] for r in rows)
            revenue = sum(float(r["price"]) * r["units"] for r in rows)
            cost_basis = item.get("product_evidence", item.get("product", {})).get("cost", item.get("cost"))
            if cost_basis is None:
                self._save(item, "excluded", {**window, "reason": "Decision-time cost evidence is missing."})
                continue
            cost = float(cost_basis)
            error = abs(units - forecast["units"]["mean"]) / max(forecast["units"]["mean"], 1.)
            result = {**window, "units": units, "revenue": revenue, "gross_profit": revenue - units * cost,
                      "absolute_percentage_error": error,
                      "interval_covered": forecast["units"]["lower"] <= units <= forecast["units"]["upper"],
                      "forecast_units": forecast["units"]["mean"], "observed_days": horizon,
                      "provenance_hash": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()}
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                duplicate = db.execute("SELECT 1 FROM observed_days WHERE sku=? AND day>=? AND day<? LIMIT 1",
                                       (item["sku"], start.isoformat(), end.isoformat())).fetchone()
                if duplicate:
                    self._save_in(db, item, "excluded", {**window, "reason": "Overlapping observations were already counted."})
                    continue
                db.executemany("INSERT INTO observed_days VALUES(?,?,?)", [(item["sku"], d, item["id"]) for d in days])
                self._save_in(db, item, "observed", result)
                self._learn(db, item, result)
        return {"items": self.outcomes(), "learning": self.states()}

    def _save(self, item, status, result):
        with self.store.connection() as db:
            self._save_in(db, item, status, result)

    def _save_in(self, db, item, status, result):
        db.execute("INSERT INTO realized_outcomes VALUES(?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET "
                   "status=excluded.status,result=excluded.result,updated_at=excluded.updated_at",
                   (item["id"], item["sku"], item["run_id"], status, json.dumps(result), now()))
        self.store._audit(db, "system", "feedback_" + status, item["run_id"],
                          {"item_id": item["id"], "sku": item["sku"], **result})

    def _learn(self, db, item, outcome):
        previous = db.execute("SELECT state,version FROM learning_versions WHERE sku=? ORDER BY version DESC LIMIT 1",
                              (item["sku"],)).fetchone()
        before = json.loads(previous["state"]) if previous else {}
        version = previous["version"] + 1 if previous else 1
        n = before.get("observations", 0) + 1
        errors = (before.get("error_series", []) + [outcome["absolute_percentage_error"]])[-20:]
        observed_days = before.get("observed_days", 0) + outcome["observed_days"]
        offset = before.get("elasticity_offset", 0.)
        delta = math.log(float(item["proposed_price"]) / float(item["current_price"]))
        adjustment = 0.
        if n >= 3 and observed_days >= 30 and abs(delta) >= math.log(1.02):
            residual = math.log(max(outcome["units"], 1.) / max(outcome["forecast_units"], 1.))
            adjustment = max(-.1, min(.1, .1 * residual / delta))
        offset = max(-.5, min(.5, offset + adjustment))
        mean_error = sum(errors) / len(errors)
        # Poor evidence widens uncertainty; it never narrows merely because a run occurred.
        calibration_ready = n >= 3 and observed_days >= 30
        multiplier = max(.75, min(2., 1 + mean_error - .15)) if calibration_ready else 1.
        widening = len(errors) >= 6 and sum(errors[-3:]) > sum(errors[-6:-3])
        state = {"version": f"learned-{version}", "observations": n, "observed_days": observed_days,
                 "elasticity_offset": offset, "last_adjustment": adjustment, "adjustment_cap": .1,
                 "cumulative_cap": .5, "uncertainty_multiplier": multiplier, "uncertainty_floor": .75,
                 "calibration_ready": calibration_ready, "minimum_observed_days": 30,
                 "mean_absolute_error": mean_error, "error_series": errors,
                 "convergence": "widening" if widening else "insufficient" if len(errors) < 6 else "stable_or_improving",
                 "method": "bounded aggregate residual calibration; observational, not causal proof"}
        db.execute("INSERT INTO learning_versions VALUES(?,?,?,?,?)",
                   (item["sku"], version, item["id"], now(), json.dumps(state)))
        self.store._audit(db, "system", "learning_updated", item["run_id"],
                          {"sku": item["sku"], "source_id": item["id"], "before": before, "after": state})

"""Explicit-start, lifespan-owned nonoverlapping interval sessions. Never restart timers."""

import asyncio
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from platform_app.config import RunRequest
from platform_app.storage import now


class LoopRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: RunRequest
    interval_seconds: int = Field(default=60, ge=5, le=86400)
    max_iterations: int | None = Field(default=None, ge=1, le=1000)


class IntervalLoop:
    def __init__(self, store, workflow, feedback, governance):
        self.store, self.workflow, self.feedback, self.governance = store, workflow, feedback, governance
        self.task = None
        self.session = None
        with store.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS loop_sessions(id TEXT PRIMARY KEY,created_at TEXT,state TEXT)")
            db.execute("CREATE TABLE IF NOT EXISTS loop_iterations(session_id TEXT,iteration INTEGER,run_id TEXT,status TEXT,"
                       "PRIMARY KEY(session_id,iteration))")
            rows = db.execute("SELECT id,state FROM loop_sessions").fetchall()
            for row in rows:
                state = json.loads(row["state"])
                if state["status"] in {"running", "waiting"}:
                    state.update(status="interrupted", running=False, next_run_at=None,
                                 error="Application restarted. Scheduling is off; explicitly start a new session.")
                    db.execute("UPDATE loop_sessions SET state=? WHERE id=?", (json.dumps(state), row["id"]))
                    store._audit(db, "system", "loop_interrupted", None, {"session_id": row["id"]})

    def state(self):
        if self.session:
            return {**self.session, "iterations": self._iterations(self.session["session_id"])}
        with self.store.connection() as db:
            row = db.execute("SELECT state FROM loop_sessions ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            saved = json.loads(row["state"])
            return {**saved, "running": False, "next_run_at": None, "iterations": self._iterations(saved["session_id"])}
        return {"running": False, "status": "off", "session_id": None, "iteration_count": 0,
                "interval_seconds": 60, "max_iterations": None, "next_run_at": None, "last_run_id": None,
                "request": None, "error": None, "iterations": []}

    def _iterations(self, session_id):
        with self.store.connection() as db:
            rows = db.execute("SELECT i.iteration,i.run_id,coalesce(r.status,i.status) status FROM loop_iterations i "
                              "LEFT JOIN runs r ON r.id=i.run_id WHERE session_id=? ORDER BY iteration DESC LIMIT 100",
                              (session_id,)).fetchall()
            results = []
            for row in rows:
                try:
                    counts = db.execute("SELECT count(*) total,coalesce(sum(json_extract(s.approval,'$.kind')='automatic'),0) auto_approved,"
                                        "coalesce(sum(s.status IN ('pending_review','hold','escalated')),0) queued,"
                                        "coalesce(sum(s.status='applied'),0) applied,coalesce(sum(s.status='unknown'),0) unknown,"
                                        "coalesce(sum(s.status='blocked'),0) blocked,coalesce(sum(s.status='unchanged'),0) unchanged FROM recommendation_state s "
                                        "JOIN recommendations r ON s.id=r.id AND s.revision=r.revision WHERE r.run_id=?",
                                        (row["run_id"],)).fetchone()
                    counts = dict(counts)
                except Exception:
                    counts = {"status": "unavailable"}
                results.append({**dict(row), "decisions": counts})
            return results

    def _persist(self, action):
        with self.store.connection() as db:
            db.execute("INSERT INTO loop_sessions VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                       (self.session["session_id"], self.session["created_at"], json.dumps(self.session)))
            self.store._audit(db, "system", action, self.session.get("last_run_id"), self.session)

    def start(self, payload: LoopRequest):
        if self.task and not self.task.done():
            raise RuntimeError("The continuous loop is already running.")
        if self.workflow.preview.busy:
            raise RuntimeError("Wait for the active analysis before starting a loop.")
        if payload.request.kind != "grounded":
            raise ValueError("The continuous loop requires the full grounded pipeline.")
        self.session = {"session_id": str(uuid4()), "created_at": now(), "running": True,
                        "status": "running", "iteration_count": 0, "interval_seconds": payload.interval_seconds,
                        "max_iterations": payload.max_iterations, "request": payload.request.model_dump(),
                        "next_run_at": None, "last_run_id": None, "error": None}
        self._persist("loop_started")
        self.task = asyncio.create_task(self._run(payload))
        return self.state()

    async def _run(self, payload):
        try:
            while self.session["running"]:
                await self.feedback.refresh(self.governance.queue())
                run = self.workflow.start(payload.request)
                self.session.update(status="running", next_run_at=None, last_run_id=run["id"])
                with self.store.connection() as db:
                    db.execute("INSERT INTO loop_iterations VALUES(?,?,?,?)", (self.session["session_id"],
                               self.session["iteration_count"] + 1, run["id"], "running"))
                self._persist("loop_iteration_started")
                while True:
                    await asyncio.sleep(.1)
                    current = self.store.get_run(run["id"])
                    if current["status"] not in {"queued", "running"}:
                        break
                self.session["iteration_count"] += 1
                with self.store.connection() as db:
                    db.execute("UPDATE loop_iterations SET status=? WHERE session_id=? AND iteration=?",
                               (current["status"], self.session["session_id"], self.session["iteration_count"]))
                if current["status"] not in {"completed", "awaiting_review"}:
                    raise RuntimeError(current["error"] or "The iteration failed or was interrupted.")
                self._persist("loop_iteration_completed")
                maximum = payload.max_iterations
                if maximum and self.session["iteration_count"] >= maximum:
                    self.session.update(running=False, status="completed", next_run_at=None)
                    self._persist("loop_completed")
                    return
                self.session.update(status="waiting", next_run_at=(datetime.now(timezone.utc) +
                                    timedelta(seconds=payload.interval_seconds)).isoformat())
                self._persist("loop_waiting")
                await asyncio.sleep(payload.interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.session.update(running=False, status="failed", next_run_at=None,
                                error="Loop iteration failed. Check the run and service health before explicitly restarting.")
            self._persist("loop_failed")

    async def stop(self, reason="operator"):
        if self.task and not self.task.done():
            self.session.update(running=False, status="stopped", next_run_at=None, stop_reason=reason)
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self._persist("loop_stopped")
        return self.state()

    async def observe_failures(self):
        with self.store.connection() as db:
            db.execute("UPDATE loop_iterations SET status=coalesce((SELECT status FROM runs WHERE runs.id=loop_iterations.run_id),status)")
            failures = db.execute("SELECT DISTINCT l.* FROM loop_sessions l JOIN loop_iterations i ON l.id=i.session_id "
                                  "WHERE i.status IN ('failed','interrupted')").fetchall()
        for row in failures:
            session = json.loads(row["state"])
            if session["status"] not in {"running", "waiting", "completed"}:
                continue
            if self.session and self.session["session_id"] == row["id"]:
                await self.stop("iteration_failed")
                self.session.update(status="failed", error="A session iteration failed. Inspect its run and explicitly restart.")
                self._persist("loop_failed")
            else:
                session.update(status="failed", running=False, next_run_at=None,
                               error="A queued iteration later failed. Inspect its run; scheduling remains off.")
                with self.store.connection() as db:
                    db.execute("UPDATE loop_sessions SET state=? WHERE id=?", (json.dumps(session), row["id"]))
                    self.store._audit(db, "system", "loop_late_failure", None, {"session_id": row["id"]})

    def history(self):
        with self.store.connection() as db:
            rows = db.execute("SELECT state FROM loop_sessions ORDER BY created_at DESC").fetchall()
        return [{**json.loads(r["state"]), "iterations": self._iterations(json.loads(r["state"])["session_id"])} for r in rows]

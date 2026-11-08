"""Own all three local child processes and stop them together."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

from scripts.preflight import ROOT, check
from scripts.runtime import node_runtime


def wait_for(url: str, process: subprocess.Popen, timeout=20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited before becoming healthy ({url}). Check its output above.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    body = response.read()
                    return json.loads(body) if "json" in response.headers.get("Content-Type", "") else {}
        except (OSError, ValueError):
            time.sleep(.2)
    raise RuntimeError(f"Service did not become ready within {timeout}s: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-gateway", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Seed an empty Commerce database; never resets existing data.")
    args = parser.parse_args()
    os.chdir(ROOT)
    processes = []

    def stop(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        settings, messages = check(require_gateway=args.require_gateway)
        print("\n".join(messages), flush=True)
        environment = os.environ.copy()
        environment["COMMERCE_DB_PATH"] = str(settings.data_dir / "commerce.db")
        node, _, _ = node_runtime()
        environment["PATH"] = str(node.parent) + os.pathsep + environment.get("PATH", "")
        if args.seed:
            # The generator refuses to overwrite an existing product catalog.
            from commerce.seed import seed_database
            import sqlite3
            database = settings.data_dir / "commerce.db"
            populated = False
            if database.exists():
                with sqlite3.connect(database) as db:
                    tables = db.execute("SELECT name FROM sqlite_master WHERE name='products'").fetchone()
                    populated = bool(tables and db.execute("SELECT COUNT(*) FROM products").fetchone()[0])
            if not populated:
                print(seed_database(database, data_dir=settings.data_dir,
                                    as_of=datetime.now(timezone.utc).date()), flush=True)
        commands = [
            ([sys.executable, "-m", "uvicorn", "commerce.app:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"], ROOT, "http://127.0.0.1:8001/health"),
            ([sys.executable, "-m", "uvicorn", "platform_app.app:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], ROOT, "http://127.0.0.1:8000/api/health"),
            ([str(node), str(ROOT / "web/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], ROOT / "web", "http://127.0.0.1:5173"),
        ]
        for command, directory, url in commands:
            process = subprocess.Popen(command, cwd=directory, env=environment)
            processes.append(process)
            status = wait_for(url, process)
            if status.get("service") == "commerce" and not status.get("seeded"):
                raise RuntimeError("Commerce is empty. Restart with --seed to create synthetic demo data.")
        print("\nPricing workbench: http://127.0.0.1:5173\nPress Ctrl+C to stop all services.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(.5)
        raise RuntimeError("A service exited. Stopping the other services; check output above.")
    except KeyboardInterrupt:
        print("\nStopping local services...", flush=True)
    except (RuntimeError, OSError, ValueError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1
    finally:
        # A terminal interrupt may also have reached children. Repeated termination is safe.
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

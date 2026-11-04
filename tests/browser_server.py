"""Disposable loopback-only Playwright fixture. Never use for production."""

import tempfile
from pathlib import Path

import uvicorn

from swarmcompute.coordinator import auth
from swarmcompute.coordinator.app import create_app

if __name__ == "__main__":
    root = Path(tempfile.mkdtemp(prefix="swarm-browser-test-"))
    app = create_app(root)
    with app.state.db.transaction() as c:
        auth.new_user(c, "reviewer", "admin", "review-only-password")
    print(f"DISPOSABLE TEST coordinator on loopback, state: {root}")
    uvicorn.run(app, host="127.0.0.1", port=18787, access_log=False)

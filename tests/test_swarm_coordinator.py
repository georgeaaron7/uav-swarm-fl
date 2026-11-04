import hashlib
import io
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from fl.config import FLConfig
from swarmcompute.coordinator import auth
from swarmcompute.coordinator import models as m
from swarmcompute.coordinator.app import create_app
from swarmcompute.coordinator.database import get, insert, put, rows
from swarmcompute.coordinator.studies import create_study
from swarmcompute.shared.hashing import config_hash, job_id


@pytest.fixture
def cluster(tmp_path):
    app = create_app(tmp_path)
    with app.state.db.transaction() as c:
        auth.new_user(c, "admin", "admin", "correct-horse")
        insert(
            c,
            m.settings,
            id="coordinator",
            data={"retry_delay": 1, "disk_critical_bytes": 1},
        )
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "correct-horse"},
        )
        admin = {"Authorization": "Bearer " + login.json()["token"]}
        yield app, client, admin


def enroll(client, admin, name="laptop"):
    code = client.post(
        "/api/v1/enrollment-codes", json={"owner": "owner"}, headers=admin
    ).json()["code"]
    payload = {
        "code": code,
        "name": name,
        "capabilities": {
            "ready": True,
            "cuda": True,
            "source_sha256": "source",
            "datasets": {"dataset_sha256": "data", "trace_sha256": None},
        },
        "preferences": {},
    }
    response = client.post("/api/v1/workers/enroll", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    client.post(
        f"/api/v1/workers/{body['worker_id']}/control",
        headers={"Authorization": "Bearer " + body["credential"]},
        json={"action": "resume"},
    )
    return body["worker_id"], {"Authorization": "Bearer " + body["credential"]}, payload


def seed_jobs(app, n=2):
    cfg = asdict(FLConfig(rounds=2))
    manifest = {
        "study": "test-study",
        "source_sha256": "source",
        "dataset_sha256": "data",
        "trace_sha256": None,
        "jobs": [
            {
                "scenario": "clean_hfl_ideal",
                "seed": i,
                "config": {**cfg, "seed": i, "name": f"run{i}"},
            }
            for i in range(n)
        ],
    }
    with app.state.db.transaction() as c:
        id = create_study(c, manifest)
        study = get(c, m.studies, id)
        study["data"]["status"] = "RUNNING"
        put(c, m.studies, study)
        for job in rows(c, m.jobs):
            job["status"] = "QUEUED"
            put(c, m.jobs, job)
    return id


def claim(client, wid, headers):
    response = client.post(f"/api/v1/workers/{wid}/jobs/claim", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["assignment"]


def test_identity_excludes_machine_paths():
    a = asdict(FLConfig())
    b = {
        **a,
        "out_dir": "C:/somewhere",
        "data_dir": "/other",
        "channel_trace_path": "/trace",
        "threads": 2,
        "device": "cuda",
    }
    assert config_hash(a) == config_hash(b)
    assert job_id("s", a, {"data": "x"}, "rev") == job_id("s", b, {"data": "x"}, "rev")
    assert job_id("s", a, {}, "rev") != job_id("s", {**a, "seed": 7}, {}, "rev")


def test_auth_enrollment_ownership_and_expiry(cluster):
    app, client, admin = cluster
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/workers").status_code == 401
    wid, h, payload = enroll(client, admin)
    assert client.post("/api/v1/workers/enroll", json=payload).status_code == 401
    assert client.get("/api/v1/settings", headers=h).status_code == 403
    assert (
        client.post("/api/v1/workers/another/jobs/claim", headers=h).status_code == 403
    )
    assert (
        client.post(
            f"/api/v1/workers/{wid}/control", headers=admin, json={"action": "pause"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/workers/{wid}/control", headers=h, json={"action": "pause"}
        ).status_code
        == 200
    )
    with app.state.db.transaction() as c:
        code = auth.token()
        insert(
            c,
            m.enrollments,
            id=auth.fingerprint(code),
            expires=time.time() - 1,
            data={"owner": "o", "redeemed": False},
        )
    assert (
        client.post(
            "/api/v1/workers/enroll", json={**payload, "code": code}
        ).status_code
        == 401
    )


def test_assignment_heartbeat_pause_and_fifo(cluster):
    app, client, admin = cluster
    w1, h1, _ = enroll(client, admin)
    w2, h2, _ = enroll(client, admin, "second")
    seed_jobs(app)
    a = claim(client, w1, h1)
    b = claim(client, w2, h2)
    assert a["job_id"] != b["job_id"]
    assert claim(client, w1, h1) is None
    response = client.post(
        f"/api/v1/workers/{w1}/heartbeat",
        headers=h1,
        json={
            "attempt_id": a["attempt_id"],
            "fence": a["fence"],
            "telemetry": {"gpu_temperature": 72},
        },
    )
    assert response.json()["lease_expires"] > a["lease_expires"]
    assert (
        client.post(
            f"/api/v1/attempts/{a['attempt_id']}/progress",
            headers=h2,
            json={"fence": a["fence"], "round": 1},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/attempts/{a['attempt_id']}/progress",
            headers=h1,
            json={"fence": a["fence"], "round": 1, "metrics": {"test_acc": 0.3}},
        ).status_code
        == 200
    )


def test_expiry_restart_and_stale_attempt_fencing(cluster, tmp_path):
    app, client, admin = cluster
    w1, h1, _ = enroll(client, admin)
    w2, h2, _ = enroll(client, admin, "second")
    seed_jobs(app, 1)
    a = claim(client, w1, h1)
    with app.state.db.transaction() as c:
        row = get(c, m.attempts, a["attempt_id"])
        row["expires"] = time.time() - 2
        put(c, m.attempts, row)
        app.state.scheduler.reconcile(c)
        job = get(c, m.jobs, a["job_id"])
        job["data"]["retry_at"] = 0
        put(c, m.jobs, job)
    # Reopen persistent DB through a new app, as after coordinator failure.
    restarted = create_app(tmp_path)
    with restarted.state.db.transaction() as c:
        b = restarted.state.scheduler.claim(c, w2)
        assert b["job_id"] == a["job_id"] and b["fence"] != a["fence"]
    for endpoint, body in [
        ("progress", {"round": 1}),
        ("fail", {"reason": "infrastructure"}),
        ("release", {}),
    ]:
        assert (
            client.post(
                f"/api/v1/attempts/{a['attempt_id']}/{endpoint}",
                headers=h1,
                json={"fence": a["fence"], **body},
            ).status_code
            == 409
        )
    assert (
        client.post(
            f"/api/v1/workers/{w1}/heartbeat",
            headers=h1,
            json={"attempt_id": a["attempt_id"], "fence": a["fence"]},
        ).status_code
        == 409
    )


def test_concurrent_claims_have_one_owner(cluster):
    app, client, admin = cluster
    w1, _, _ = enroll(client, admin)
    w2, _, _ = enroll(client, admin, "second")
    seed_jobs(app, 1)

    def acquire(w):
        with app.state.db.transaction() as c:
            return app.state.scheduler.claim(c, w)

    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(acquire, [w1, w2]))
    assert sum(c is not None for c in claims) == 1


def test_oom_requires_attention_not_selective_retry(cluster):
    app, client, admin = cluster
    w, h, _ = enroll(client, admin)
    seed_jobs(app, 1)
    a = claim(client, w, h)
    r = client.post(
        f"/api/v1/attempts/{a['attempt_id']}/fail",
        headers=h,
        json={"fence": a["fence"], "reason": "cuda_oom"},
    )
    assert r.status_code == 200
    with app.state.db.transaction() as c:
        assert get(c, m.jobs, a["job_id"])["status"] == "NEEDS_ATTENTION"


def test_path_traversal_and_upload_hash(cluster):
    app, client, admin = cluster
    w, h, _ = enroll(client, admin)
    seed_jobs(app, 1)
    a = claim(client, w, h)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("../evil", "bad")
    raw = data.getvalue()
    u = client.post(
        f"/api/v1/attempts/{a['attempt_id']}/uploads",
        headers=h,
        json={
            "fence": a["fence"],
            "kind": "checkpoint",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    ).json()
    headers = {**h, "X-Lease-Token": a["fence"]}
    assert (
        client.put(
            f"/api/v1/uploads/{u['id']}", headers=headers, content=raw
        ).status_code
        == 200
    )
    result = client.post(
        f"/api/v1/uploads/{u['id']}/finalize", headers=h, json={"fence": a["fence"]}
    )
    assert result.status_code == 400 and "unsafe" in result.text


def test_settings_request_limits_and_owner_leave(cluster):
    app, client, admin = cluster
    worker, headers, _ = enroll(client, admin)
    assert (
        client.put(
            "/api/v1/settings", headers=admin, json={"lease_timeout": 1}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            content=b"x" * (1024 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            f"/api/v1/workers/{worker}/control",
            headers=headers,
            json={"action": "leave"},
        ).status_code
        == 200
    )
    heartbeat = client.post(
        f"/api/v1/workers/{worker}/heartbeat", headers=headers, json={}
    ).json()
    assert heartbeat["leaving"] is True
    assert (
        client.post(f"/api/v1/workers/{worker}/revoke", headers=headers).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/workers/{worker}/heartbeat", headers=headers, json={}
        ).status_code
        == 401
    )


def test_owner_preferences_are_acknowledged_and_admin_cannot_self_grant(cluster):
    app, client, admin = cluster
    worker, headers, _ = enroll(client, admin)
    path = f"/api/v1/workers/{worker}/preferences"
    assert client.put(path, headers=admin, json={"mode": "light"}).status_code == 403
    assert (
        client.put(
            path,
            headers=headers,
            json={"mode": "light", "admin_permissions": ["preferences"]},
        ).status_code
        == 200
    )
    h = client.post(
        f"/api/v1/workers/{worker}/heartbeat",
        headers=headers,
        json={"preferences": {"mode": "balanced"}},
    ).json()
    assert h["preferences_update"]["mode"] == "light"
    assert h["preferences_update"]["cpu_threads"] == 1
    version = h["preferences_version"]
    acknowledged = client.post(
        f"/api/v1/workers/{worker}/heartbeat",
        headers=headers,
        json={"preferences": h["preferences_update"], "preferences_version": version},
    ).json()
    assert acknowledged["preferences_update"] is None
    assert (
        client.put(
            path, headers=admin, json={"admin_permissions": ["leave"]}
        ).status_code
        == 403
    )
    assert (
        client.put(path, headers=admin, json={"mode": "dedicated"}).status_code == 200
    )
    assert client.put(path, headers=headers, json={"cpu_threads": 0}).status_code == 422

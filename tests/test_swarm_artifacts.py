import csv
import hashlib
import io
import json
import time
import zipfile
from dataclasses import asdict

import pytest
from test_checkpoint_resume import make_server
from test_swarm_coordinator import claim, enroll, seed_jobs
from test_swarm_coordinator import cluster as cluster

from fl.checkpoint import save_checkpoint
from swarmcompute.coordinator import models as m
from swarmcompute.coordinator.database import get, put, rows
from swarmcompute.shared.hashing import config_hash


def bundle(files):
    value = io.BytesIO()
    with zipfile.ZipFile(value, "w") as z:
        for name, raw in files.items():
            z.writestr(name, raw)
    return value.getvalue()


def upload(client, headers, assignment, raw, kind):
    r = client.post(
        f"/api/v1/attempts/{assignment['attempt_id']}/uploads",
        headers=headers,
        json={
            "fence": assignment["fence"],
            "kind": kind,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
        },
    )
    assert r.status_code == 200, r.text
    id = r.json()["id"]
    split = len(raw) // 2
    for offset, part in [(0, raw[:split]), (split, raw[split:])]:
        response = client.put(
            f"/api/v1/uploads/{id}?offset={offset}",
            headers={**headers, "X-Lease-Token": assignment["fence"]},
            content=part,
        )
        assert response.status_code == 200, response.text
    return id, client.post(
        f"/api/v1/uploads/{id}/finalize",
        headers=headers,
        json={"fence": assignment["fence"]},
    )


def result(assignment, diverged=False):
    cfg = assignment["config"]
    history = (
        []
        if diverged
        else [
            {"round": i, "test_acc": 0.2, "train_loss": 1.0, "test_loss": 2.0}
            for i in range(1, 3)
        ]
    )
    summary = {
        "diverged": diverged,
        "completed_rounds": len(history),
        "divergence_round": 1 if diverged else None,
        "divergence_stage": "client 1 local training" if diverged else None,
        "final_test_acc": None if diverged else 0.2,
    }
    runtime = {
        "config_sha256": config_hash(cfg),
        "source_sha256": "source",
        "dataset_sha256": "data",
        "trace_sha256": None,
        "provenance": {
            "job_id": assignment["job_id"],
            "attempt_id": assignment["attempt_id"],
        },
    }
    csv_data = io.StringIO()
    w = csv.DictWriter(
        csv_data, fieldnames=["round", "test_acc", "train_loss", "test_loss"]
    )
    w.writeheader()
    w.writerows(history)
    import torch

    model = io.BytesIO()
    torch.save({"weight": torch.zeros(2)}, model)
    return bundle(
        {
            "config.json": json.dumps(cfg),
            "summary.json": json.dumps(summary),
            "history.json": json.dumps(history),
            "runtime.json": json.dumps(runtime),
            "metrics.csv": csv_data.getvalue(),
            "final_model.pt": model.getvalue(),
        }
    )


@pytest.mark.parametrize("diverged", [False, True])
def test_terminal_publication_is_validated_idempotent_and_immutable(cluster, diverged):
    app, client, admin = cluster
    w, h, _ = enroll(client, admin)
    seed_jobs(app, 1)
    a = claim(client, w, h)
    id, r = upload(client, h, a, result(a, diverged), "result")
    assert r.status_code == 200, r.text
    for _ in range(2):
        r = client.post(
            f"/api/v1/attempts/{a['attempt_id']}/complete",
            headers=h,
            json={"fence": a["fence"], "artifact_id": id},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == ("DIVERGED" if diverged else "SUCCEEDED")
    assert claim(client, w, h) is None
    r = client.post(
        f"/api/v1/attempts/{a['attempt_id']}/fail",
        headers=h,
        json={"fence": a["fence"], "reason": "infrastructure"},
    )
    assert r.status_code == 409
    with app.state.db.transaction() as c:
        assert len([j for j in rows(c, m.jobs) if j["data"]["result"] == id]) == 1
        assert get(c, m.jobs, a["job_id"])["data"]["retry_count"] == 0


def test_corrupt_checksum_cannot_publish(cluster):
    app, client, admin = cluster
    w, h, _ = enroll(client, admin)
    seed_jobs(app, 1)
    a = claim(client, w, h)
    raw = result(a)
    r = client.post(
        f"/api/v1/attempts/{a['attempt_id']}/uploads",
        headers=h,
        json={
            "fence": a["fence"],
            "kind": "result",
            "sha256": "f" * 64,
            "size": len(raw),
        },
    )
    id = r.json()["id"]
    client.put(
        f"/api/v1/uploads/{id}", headers={**h, "X-Lease-Token": a["fence"]}, content=raw
    )
    assert (
        client.post(
            f"/api/v1/uploads/{id}/finalize", headers=h, json={"fence": a["fence"]}
        ).status_code
        == 400
    )
    with app.state.db.transaction() as c:
        assert get(c, m.jobs, a["job_id"])["data"]["result"] is None


def test_recovery_falls_back_from_corrupted_checkpoint(cluster, tmp_path):
    app, client, admin = cluster
    w, h, _ = enroll(client, admin)
    seed_jobs(app, 1)
    a = claim(client, w, h)
    cp = make_server("fedavg")
    # Make the queued test job match the real simulator checkpoint identity.
    from fl.checkpoint import identity

    with app.state.db.transaction() as c:
        j = get(c, m.jobs, a["job_id"])
        j["data"].update(
            config=asdict(cp.cfg),
            config_hash=identity(cp.cfg)["config_sha256"],
            source_sha256=identity(cp.cfg)["source_sha256"],
            datasets={"dataset_sha256": None, "trace_sha256": None},
        )
        put(c, m.jobs, j)
    output = tmp_path / "run"
    output.mkdir()
    ids = []

    class Stop(Exception):
        pass

    def callback(server, record):
        path = save_checkpoint(
            server,
            tmp_path / "checkpoints",
            {"job_id": a["job_id"], "attempt_id": a["attempt_id"]},
        )
        id, r = upload(
            client,
            h,
            a,
            bundle(
                {
                    name: (path / name).read_bytes()
                    for name in ["state.pt", "metadata.json", "COMPLETE"]
                }
            ),
            "checkpoint",
        )
        assert r.status_code == 200, r.text
        ids.append(id)
        if record["round"] == 2:
            raise Stop()

    with pytest.raises(Stop):
        cp.run(str(output), callback)
    with app.state.db.transaction() as c:
        latest = get(c, m.checkpoints, ids[-1])
        (app.state.db.root / latest["data"]["path"]).write_bytes(b"corrupt")
        job = get(c, m.jobs, a["job_id"])
        recovered = app.state.scheduler.valid_checkpoint(c, job)
        assert recovered["id"] == ids[0] and recovered["round"] == 1
        assert get(c, m.checkpoints, ids[-1])["data"]["valid"] is False


def test_worker_dies_during_round_37_recovery_uses_round_30(cluster, tmp_path):
    app, client, admin = cluster
    w1, h1, _ = enroll(client, admin)
    w2, h2, _ = enroll(client, admin, "replacement")
    seed_jobs(app, 1)
    a = claim(client, w1, h1)
    server = make_server("ccra", 100)
    from fl.checkpoint import identity

    cap = {
        "ready": True,
        "cuda": True,
        "source_sha256": identity(server.cfg)["source_sha256"],
        "datasets": {"dataset_sha256": None, "trace_sha256": None},
    }
    with app.state.db.transaction() as c:
        j = get(c, m.jobs, a["job_id"])
        j["data"].update(
            config=asdict(server.cfg),
            config_hash=identity(server.cfg)["config_sha256"],
            source_sha256=cap["source_sha256"],
            datasets=cap["datasets"],
        )
        put(c, m.jobs, j)
        w = get(c, m.workers, w2)
        w["data"]["capabilities"] = cap
        put(c, m.workers, w)
    run = tmp_path / "original"
    run.mkdir()

    class Killed(Exception):
        pass

    def callback(s, record):
        if record["round"] % 10 == 0:
            path = save_checkpoint(
                s,
                tmp_path / "checkpoints",
                {"job_id": a["job_id"], "attempt_id": a["attempt_id"]},
            )
            _, r = upload(
                client,
                h1,
                a,
                bundle(
                    {
                        n: (path / n).read_bytes()
                        for n in ["state.pt", "metadata.json", "COMPLETE"]
                    }
                ),
                "checkpoint",
            )
            assert r.status_code == 200, r.text

    # Inject the death inside round 37, before any round-37 state is committed.
    original = server.channel.link_state

    def fail_at_round(rnd):
        if rnd == 37:
            raise Killed()
        return original(rnd)

    server.channel.link_state = fail_at_round
    with pytest.raises(Killed):
        server.run(str(run), callback)
    with app.state.db.transaction() as c:
        row = get(c, m.attempts, a["attempt_id"])
        row["expires"] = time.time() - 1
        put(c, m.attempts, row)
        app.state.scheduler.reconcile(c)
        j = get(c, m.jobs, a["job_id"])
        j["data"]["retry_at"] = 0
        put(c, m.jobs, j)
    b = claim(client, w2, h2)
    assert b["checkpoint"]["round"] == 30
    response = client.get(
        "/api/v1/artifacts/" + b["checkpoint"]["id"] + "/download", headers=h2
    )
    assert response.status_code == 200
    archive_path = tmp_path / "recovery.zip"
    archive_path.write_bytes(response.content)
    from swarmcompute.worker.executor import extract_checkpoint

    path = extract_checkpoint(archive_path, tmp_path / "recovered")
    from fl.checkpoint import load_checkpoint, restore_rng

    state, rng, _ = load_checkpoint(path, identity(server.cfg))
    replacement = make_server("ccra", 100)
    replacement.load_state_dict(state)
    restore_rng(rng)
    out = tmp_path / "replacement"
    out.mkdir()
    replacement.run(str(out))
    assert replacement.history[30]["round"] == 31
    assert [r["round"] for r in replacement.history] == list(range(1, 101))
    assert (
        client.post(
            f"/api/v1/attempts/{a['attempt_id']}/progress",
            headers=h1,
            json={"fence": a["fence"], "round": 37},
        ).status_code
        == 409
    )


def test_unavailable_storage_never_commits_result(cluster, monkeypatch):
    app, client, admin = cluster
    worker, headers, _ = enroll(client, admin)
    seed_jobs(app, 1)
    assignment = claim(client, worker, headers)

    def unavailable(*args, **kwargs):
        raise PermissionError("injected artifact storage outage")

    monkeypatch.setattr("swarmcompute.coordinator.artifacts.os.replace", unavailable)
    with pytest.raises(PermissionError):
        upload(client, headers, assignment, result(assignment), "result")
    with app.state.db.transaction() as c:
        assert get(c, m.jobs, assignment["job_id"])["data"]["result"] is None
        assert not any(a["data"]["valid"] for a in rows(c, m.artifacts))

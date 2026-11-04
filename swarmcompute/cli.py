from __future__ import annotations

import json
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Annotated

import httpx
import typer

from . import PROTOCOL_VERSION, __version__
from .config import data_home, read_config, worker_home, write_config

app = typer.Typer(
    no_args_is_help=True,
    help="SwarmCompute: independent experiments across voluntary GPU workers.",
)
server = typer.Typer(no_args_is_help=True)
study = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
autostart = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(
    no_args_is_help=True,
    help="Export or verify an explicit offline prepared-data handoff.",
)
app.add_typer(data_app, name="data")


@data_app.command("export")
def data_export(
    destination: Annotated[Path, typer.Option()], data_dir: Path = Path("data")
):
    from .datasets import export_data

    output(export_data(data_dir, destination))


@data_app.command("verify")
def data_verify(data_dir: Path = Path("data")):
    from .datasets import verify_data

    report = verify_data(data_dir)
    output(report)
    if not report["valid"]:
        raise typer.Exit(1)


app.add_typer(server, name="server")
app.add_typer(study, name="study")
app.add_typer(config_app, name="config")
app.add_typer(autostart, name="autostart")


def output(value):
    typer.echo(json.dumps(value, indent=2, default=str))


def coordinator():
    from .coordinator.database import Database

    return Database(data_home())


def urls(port=8787, qr=False):
    from .network import addresses

    found = addresses(port)
    for a in found:
        typer.echo(f"{a['kind']}: {a['url']}")
    if qr:
        import qrcode

        url = next((a["url"] for a in found if a["kind"] == "LAN"), found[0]["url"])
        image = qrcode.QRCode(border=1)
        image.add_data(url)
        image.print_ascii(invert=True)
    typer.echo(
        "Addresses are detected interfaces; verify firewall and peer connectivity."
    )


@server.command("init")
def server_init(username: str = "admin", port: int = 8787):
    from .coordinator import auth
    from .coordinator import models as m
    from .coordinator.database import insert, rows

    db = coordinator()
    if os.name != "nt":
        db.root.chmod(0o700)
    with db.transaction() as c:
        if rows(c, m.users):
            raise typer.BadParameter("coordinator already initialized")
        user, password = auth.new_user(c, username, "admin")
        insert(c, m.settings, id="coordinator", data={})
    probe = db.root / ".write-test"
    probe.write_text("ok")
    probe.unlink()
    typer.echo(
        f"Initialized {db.root}; free storage {shutil.disk_usage(db.root).free / 1024**3:.1f} GiB"
    )
    typer.echo(f"Administrator: {username}\nInitial password (shown once): {password}")
    urls(port, True)


@server.command("reset-password")
def server_reset_password(username: Annotated[str, typer.Option()] = "admin"):
    """Local recovery: set a password for an existing account and revoke its sessions."""
    from .coordinator import auth
    from .coordinator import models as m
    from .coordinator.database import put, rows
    from .coordinator.scheduler import event

    password = typer.prompt(
        "New password (at least 12 characters)",
        hide_input=True,
        confirmation_prompt=True,
    )
    if not 12 <= len(password) <= 256:
        raise typer.BadParameter("password must contain 12–256 characters")
    with coordinator().transaction() as c:
        user = next((u for u in rows(c, m.users) if u["username"] == username), None)
        if not user:
            raise typer.BadParameter("unknown username")
        user["data"]["password_hash"] = auth.hasher.hash(password)
        put(c, m.users, user)
        c.execute(m.sessions.delete().where(m.sessions.c.user_id == user["id"]))
        event(c, "password_reset_locally", user_id=user["id"])
    typer.echo("Password updated; existing sessions revoked. Sign in again.")


@server.command("start")
def server_start(host: str = "0.0.0.0", port: int = 8787):
    from .coordinator import models as m
    from .coordinator.database import rows

    db = coordinator()
    with db.transaction() as c:
        if not rows(c, m.users):
            raise typer.BadParameter("run swarm server init first")
    urls(port)
    import uvicorn

    from .coordinator.app import create_app

    uvicorn.run(create_app(data_home()), host=host, port=port, access_log=False)


@server.command("urls")
def server_urls(port: int = 8787):
    urls(port, True)


@server.command("backup")
def server_backup():
    from .coordinator.operations import backup

    typer.echo(backup(coordinator()))


@server.command("maintain")
def server_maintain():
    from .coordinator.operations import maintain

    output({"removed": maintain(coordinator())})


@server.command("enrollment")
def server_enrollment(owner: Annotated[str, typer.Option()], ttl: int = 600):
    from .coordinator import auth
    from .coordinator import models as m
    from .coordinator.database import insert

    if ttl < 60 or ttl > 3600:
        raise typer.BadParameter("ttl must be 60–3600 seconds")
    code = auth.token()
    with coordinator().transaction() as c:
        insert(
            c,
            m.enrollments,
            id=auth.fingerprint(code),
            expires=time.time() + ttl,
            data={"owner": owner, "redeemed": False},
        )
    typer.echo(f"One-time code (expires in {ttl}s): {code}")


@study.command("create", context_settings={"allow_extra_args": True})
def study_create(
    ctx: typer.Context,
    name: str,
    profile: str = "pilot",
    aggs: Annotated[list[str] | None, typer.Option()] = None,
    data_dir: Path = Path("data"),
    trace_path: Path = Path("data/channel_traces/deepsense23.npz"),
):
    from .coordinator.studies import create_study, plan_study

    # Accept the documented '--aggs fedavg ccra' form as well as repeatable options.
    methods = (aggs or []) + ctx.args
    if not methods:
        methods = ["fedavg", "ccra"]
    try:
        manifest = plan_study(name, profile, methods, data_dir, trace_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))
    db = coordinator()
    with db.transaction() as c:
        id = create_study(c, manifest)
    path = db.root / "studies" / id
    path.mkdir()
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2))
    typer.echo(
        f"{name}: {len(manifest['jobs'])} jobs planned, awaiting explicit start.\nReview: {path / 'manifest.json'}"
    )


def find_study(c, name):
    from .coordinator import models as m
    from .coordinator.database import rows

    row = next(
        (s for s in rows(c, m.studies) if s["name"] == name or s["id"] == name), None
    )
    if not row:
        raise typer.BadParameter("unknown study")
    return row


def control_study(name, action):
    from .coordinator import models as m
    from .coordinator.database import put, rows

    with coordinator().transaction() as c:
        row = find_study(c, name)
        row["data"]["status"] = "PAUSED" if action == "pause" else "RUNNING"
        put(c, m.studies, row)
        if action != "pause":
            for job in rows(c, m.jobs):
                if job["study_id"] == row["id"] and job["status"] == "PENDING":
                    job["status"] = "QUEUED"
                    put(c, m.jobs, job)
    typer.echo(f"{name}: {action}")


@study.command("start")
def study_start(name: str):
    control_study(name, "start")


@study.command("pause")
def study_pause(name: str):
    control_study(name, "pause")


@study.command("resume")
def study_resume(name: str):
    control_study(name, "resume")


@study.command("status")
def study_status(name: str):
    from collections import Counter

    from .coordinator import models as m
    from .coordinator.database import rows

    with coordinator().transaction() as c:
        s = find_study(c, name)
        output(
            {
                "study": name,
                "status": s["data"]["status"],
                "jobs": dict(
                    Counter(
                        j["status"] for j in rows(c, m.jobs) if j["study_id"] == s["id"]
                    )
                ),
            }
        )


@study.command("validate")
def study_validate(name: str):
    from .coordinator.operations import validate_study

    db = coordinator()
    with db.transaction() as c:
        id = find_study(c, name)["id"]
    result = validate_study(db, id)
    output(result)
    if not result["valid"]:
        raise typer.Exit(1)


@study.command("export")
def study_export(name: str, destination: Path | None = None):
    from .coordinator.operations import export_study

    db = coordinator()
    with db.transaction() as c:
        id = find_study(c, name)["id"]
    typer.echo(export_study(db, id, destination or Path("results") / name))


def remote(method, path, **kwargs):
    cfg = read_config()
    with httpx.Client(
        base_url=cfg["server"],
        headers={"Authorization": "Bearer " + cfg["credential"]},
        timeout=15,
    ) as client:
        response = client.request(method, "/api/v1" + path, **kwargs)
        if response.status_code >= 400:
            raise typer.BadParameter(
                f"coordinator: {response.status_code} {response.text}"
            )
        return response.json()


@app.command("join")
def join(
    server: Annotated[str, typer.Option()],
    pairing_code: Annotated[str | None, typer.Option()] = None,
    name: str | None = None,
    data_dir: Path = Path("data"),
    trace_path: Path = Path("data/channel_traces/deepsense23.npz"),
    mode: str = "balanced",
    allow_cpu: bool = False,
):
    from urllib.parse import urlparse

    from .worker.resources import preferences
    from .worker.telemetry import capabilities

    parsed = urlparse(server)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        raise typer.BadParameter("server must be an HTTP(S) URL")
    if (worker_home() / "config.json").exists() and not read_config().get("left"):
        raise typer.BadParameter(
            "already enrolled; leave before joining another coordinator"
        )
    if pairing_code:
        typer.echo(
            "Pairing codes passed as arguments may remain in shell history. Prefer interactive entry."
        )
    code = pairing_code or typer.prompt("One-time enrollment code", hide_input=True)
    cfg = {
        "server": server.rstrip("/"),
        "name": name or platform.node(),
        "data_dir": str(data_dir.resolve()),
        "trace_path": str(trace_path.resolve()),
        "mode": mode,
        "allow_cpu": allow_cpu,
    }
    cap = capabilities(cfg)
    prefs = preferences(cfg)
    with httpx.Client(timeout=30) as client:
        health = client.get(server.rstrip("/") + "/health")
        health.raise_for_status()
        response = client.post(
            server.rstrip("/") + "/api/v1/workers/enroll",
            json={
                "code": code,
                "name": cfg["name"],
                "capabilities": cap,
                "preferences": prefs,
                "protocol_version": PROTOCOL_VERSION,
            },
        )
        if response.status_code != 200:
            raise typer.BadParameter(response.text)
        value = response.json()
    cfg.update(worker_id=value["worker_id"], credential=value["credential"])
    write_config(cfg)
    typer.echo(
        f"Enrolled {cfg['name']} as {cfg['worker_id']}. Run swarm doctor, then swarm start."
    )
    if value.get("owner_password"):
        typer.echo(
            f"Owner dashboard login: {value['owner_username']}\nInitial password (shown once): {value['owner_password']}"
        )
    output({"ready": cap["ready"], "diagnostics": cap["diagnostics"]})


@app.command("start")
def start():
    from .worker.agent import Agent

    Agent().run()


@app.command("status")
def status():
    cfg = read_config()
    if cfg.get("left"):
        output({"worker": cfg["worker_id"], "status": "LEFT", "credential": "revoked"})
        return
    path = worker_home() / "status.json"
    output(
        {
            "worker": cfg["worker_id"],
            "server": cfg["server"],
            "local": json.loads(path.read_text()) if path.exists() else None,
            "coordinator": remote("GET", f"/workers/{cfg['worker_id']}"),
        }
    )


def worker_control(action):
    cfg = read_config()
    result = remote(
        "POST", f"/workers/{cfg['worker_id']}/control", json={"action": action}
    )
    typer.echo(f"Worker control: {action}")
    return result


@app.command("pause")
def pause(after_round: bool = False):
    worker_control("pause" if after_round else "drain")


@app.command("resume")
def resume():
    worker_control("resume")


@app.command("leave")
def leave():
    cfg = read_config()
    worker_control("leave")
    cfg["leaving"] = True
    write_config(cfg)
    try:
        remote("POST", f"/workers/{cfg['worker_id']}/revoke")
        cfg["left"] = True
        write_config(cfg)
        typer.echo(
            "Credential revoked. Disable opted-in autostart with swarm autostart disable."
        )
    except typer.BadParameter:
        typer.echo(
            "Current work will checkpoint and release before revocation; keep swarm start running until it exits."
        )


@app.command("doctor")
def doctor():
    from .worker.telemetry import capabilities, telemetry

    cfg = (
        read_config()
        if (worker_home() / "config.json").exists()
        else {"data_dir": "data", "trace_path": "data/channel_traces/deepsense23.npz"}
    )
    cap = capabilities(cfg)
    output(
        {
            "capabilities": cap,
            "telemetry": telemetry(),
            "version": __version__,
            "protocol": PROTOCOL_VERSION,
        }
    )
    if cfg.get("server"):
        with httpx.Client(timeout=10) as client:
            output(client.get(cfg["server"] + "/health").json())
    if not cap["ready"]:
        raise typer.Exit(1)


@app.command("logs")
def logs(follow: bool = False):
    path = worker_home() / "agent.log"
    if not path.exists():
        typer.echo("No agent logs yet.")
        return
    with path.open() as handle:
        while True:
            text = handle.read()
            if text:
                typer.echo(text, nl=False)
            if not follow:
                break
            time.sleep(0.5)


@config_app.command("show")
def config_show():
    output({k: v for k, v in read_config().items() if k != "credential"})


@config_app.command("set")
def config_set(key: str, value: str):
    allowed = {
        "server": str,
        "mode": str,
        "cpu_threads": int,
        "allow_battery": bool,
        "min_battery": int,
        "max_temperature": int,
        "vram_budget_mb": int,
        "storage_limit_bytes": int,
        "data_dir": str,
        "trace_path": str,
        "admin_permissions": list,
    }
    if key not in allowed:
        raise typer.BadParameter("supported preferences: " + ", ".join(allowed))
    typ = allowed[key]
    try:
        parsed = (
            [part.strip() for part in value.split(",") if part.strip()]
            if typ is list and not value.lstrip().startswith("[")
            else json.loads(value)
            if typ in (bool, list)
            else typ(value)
        )
    except (ValueError, TypeError):
        raise typer.BadParameter("invalid value")
    if typ is int and parsed < 0:
        raise typer.BadParameter("value must be nonnegative")
    if typ in (bool, list) and type(parsed) is not typ:
        raise typer.BadParameter("incorrect value type")
    if key == "server":
        from urllib.parse import urlparse

        url = urlparse(parsed)
        if (
            url.scheme not in {"http", "https"}
            or not url.netloc
            or url.username
            or url.password
        ):
            raise typer.BadParameter(
                "server must be an HTTP(S) URL without embedded credentials"
            )
    cfg = read_config()
    cfg[key] = parsed
    if key == "mode":
        cfg.pop("cpu_threads", None)
    from .worker.resources import preferences

    preferences(cfg)
    write_config(cfg)
    typer.echo(
        "Preference saved; resource policies apply before the next assignment. Restart the agent after changing server or dataset paths."
    )


@autostart.command("enable")
def autostart_enable():
    from .worker.autostart import configure

    read_config()
    typer.echo(configure(True))


@autostart.command("disable")
def autostart_disable():
    from .worker.autostart import configure

    typer.echo(configure(False))


@app.command("version")
def version():
    typer.echo(f"SwarmCompute {__version__}; protocol {PROTOCOL_VERSION}")


@app.command("benchmark")
def benchmark():
    from dataclasses import asdict

    from fl.config import FLConfig

    from .worker.executor import launch
    from .worker.telemetry import capabilities

    cfg = read_config()
    cap = capabilities(cfg)
    if not cap["ready"]:
        raise typer.BadParameter("worker not ready; run swarm doctor")
    root = worker_home() / "benchmarks" / str(time.time_ns())
    config = asdict(
        FLConfig(name="benchmark", rounds=2, local_epochs=1, num_clients=10, threads=2)
    )
    assignment = {
        "config": config,
        "job_id": "benchmark",
        "study_id": "benchmark",
        "attempt_id": root.name,
        "settings": {"checkpoint_every_rounds": 1, "checkpoint_every_seconds": 180},
    }
    from .worker.telemetry import telemetry

    samples = []
    start = time.monotonic()
    proc, out = launch(assignment, cfg, root)
    while proc.poll() is None:
        samples.append(telemetry(root))
        time.sleep(0.5)
    code = proc.wait()
    duration = time.monotonic() - start
    if code or not (out / "summary.json").exists():
        raise typer.BadParameter(f"benchmark failed; inspect {root / 'training.log'}")
    result = {
        "kind": "benchmark_only",
        "rounds": 2,
        "duration_s": duration,
        "rounds_per_minute": 120 / duration,
        "hardware": cap,
        "summary": json.loads((out / "summary.json").read_text()),
    }
    for key in ("gpu_utilization", "cpu_percent", "gpu_memory_used_mb"):
        values = [s[key] for s in samples if s.get(key) is not None]
        result["peak_" + key] = max(values) if values else None
        result["average_" + key] = sum(values) / len(values) if values else None
    (root / "benchmark.json").write_text(json.dumps(result, indent=2))
    output(result)

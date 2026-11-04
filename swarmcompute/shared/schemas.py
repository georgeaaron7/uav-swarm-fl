from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    @model_validator(mode="after")
    def finite_payload(self):
        import json

        json.dumps(self.model_dump(), allow_nan=False)
        return self


class Login(Payload):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class Enrollment(Payload):
    owner: str = Field(min_length=1, max_length=80)
    ttl: int = Field(default=600, ge=60, le=3600)


class Enroll(Payload):
    code: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    capabilities: dict = Field(default_factory=dict)
    preferences: dict = Field(default_factory=dict)
    protocol_version: int = 1


class Heartbeat(Payload):
    preferences_version: int = Field(default=0, ge=0)
    attempt_id: str | None = None
    fence: str | None = None
    telemetry: dict = Field(default_factory=dict)
    capabilities: dict | None = None
    preferences: dict | None = None


class Fenced(Payload):
    fence: str


class Progress(Fenced):
    round: int = Field(ge=0)
    metrics: dict = Field(default_factory=dict)
    runtime: dict = Field(default_factory=dict)
    logs: str = Field(default="", max_length=65536)


class Upload(Fenced):
    kind: Literal["checkpoint", "result"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(gt=0)


class Complete(Fenced):
    artifact_id: str


class Failure(Fenced):
    reason: Literal[
        "infrastructure",
        "network",
        "shutdown",
        "cuda_oom",
        "dataset_mismatch",
        "source_mismatch",
        "application",
        "artifact_corruption",
    ]
    details: str = Field(default="", max_length=4096)


class Control(Payload):
    action: Literal["resume", "drain", "pause", "leave"]


class Study(Payload):
    name: str
    profile: Literal["pilot", "final"] = "pilot"
    aggs: list[str] = Field(default_factory=lambda: ["fedavg", "ccra"])
    data_dir: str = "data"
    trace_path: str = "data/channel_traces/deepsense23.npz"
    seeds: list[int] | None = None
    rounds: int | None = None
    attacks: list[str] | None = None
    conditions: list[str] | None = None


class Preferences(Payload):
    mode: Literal["light", "balanced", "dedicated"] | None = None
    cpu_threads: int | None = Field(default=None, ge=1, le=64)
    allow_battery: bool | None = None
    min_battery: int | None = Field(default=None, ge=0, le=100)
    max_temperature: int | None = Field(default=None, ge=40, le=100)
    vram_budget_mb: int | None = Field(default=None, ge=0)
    storage_limit_bytes: int | None = Field(default=None, ge=1024**3)
    admin_permissions: (
        list[Literal["pause", "resume", "drain", "leave", "preferences"]] | None
    ) = None

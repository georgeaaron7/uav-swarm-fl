"""SQLAlchemy Core schema. JSON records contain versioned entity payloads."""

from sqlalchemy import JSON, Column, Float, ForeignKey, Integer, MetaData, String, Table

metadata = MetaData()


def entity(name, *columns):
    return Table(
        name,
        metadata,
        Column("id", String, primary_key=True),
        *columns,
        Column("data", JSON, nullable=False),
    )


users = entity("users", Column("username", String, unique=True, nullable=False))
sessions = entity(
    "sessions", Column("user_id", ForeignKey("users.id")), Column("expires", Float)
)
enrollments = entity("enrollments", Column("expires", Float))
workers = entity(
    "workers", Column("owner_id", ForeignKey("users.id")), Column("last_seen", Float)
)
studies = entity(
    "studies", Column("name", String, unique=True), Column("created", Float)
)
jobs = entity(
    "jobs",
    Column("study_id", ForeignKey("studies.id")),
    Column("status", String, index=True),
    Column("created", Float),
)
attempts = entity(
    "attempts",
    Column("job_id", ForeignKey("jobs.id")),
    Column("worker_id", ForeignKey("workers.id")),
    Column("status", String),
    Column("expires", Float),
)
checkpoints = entity(
    "checkpoints",
    Column("job_id", ForeignKey("jobs.id")),
    Column("attempt_id", ForeignKey("attempts.id")),
    Column("round", Integer),
)
artifacts = entity(
    "artifacts", Column("attempt_id", ForeignKey("attempts.id")), Column("kind", String)
)
events = entity("events", Column("created", Float), Column("kind", String))
settings = entity("settings")

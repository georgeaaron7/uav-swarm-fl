from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select


class Database:
    def __init__(self, root, migrate=True):
        self.root = Path(root)
        (self.root / "database").mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "database/swarmcompute.db"
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def pragmas(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=FULL")
            cursor.close()

        if migrate:
            config = Config()
            config.set_main_option(
                "script_location", str(Path(__file__).parent / "migrations")
            )
            with self.engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
        for folder in ("artifacts", "uploads", "studies", "backups"):
            (self.root / folder).mkdir(exist_ok=True, mode=0o700)

    @contextmanager
    def transaction(self):
        with self.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise


def get(c, table, id):
    row = c.execute(select(table).where(table.c.id == id)).mappings().first()
    return dict(row) if row else None


def rows(c, table, where=None):
    query = select(table)
    if where is not None:
        query = query.where(where)
    return [dict(r) for r in c.execute(query).mappings()]


def put(c, table, row):
    c.execute(table.update().where(table.c.id == row["id"]).values(**row))


def insert(c, table, **row):
    c.execute(table.insert().values(**row))
    return row


def attempt_summaries(c):
    from .models import attempts

    query = select(
        attempts.c.id,
        attempts.c.job_id,
        attempts.c.worker_id,
        attempts.c.status,
        attempts.c.expires,
        attempts.c.data["started"].as_float().label("started"),
        attempts.c.data["ended"].as_float().label("ended"),
    )
    return [
        {
            "id": r.id,
            "job_id": r.job_id,
            "worker_id": r.worker_id,
            "status": r.status,
            "expires": r.expires,
            "data": {"started": r.started, "ended": r.ended},
        }
        for r in c.execute(query)
    ]

import aiosqlite
import logging
from datetime import datetime, timezone
from typing import List, Optional
from models import Job

logger = logging.getLogger(__name__)

DB_PATH = "jobs.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    apply_link TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    posted_date TEXT,
    match_score INTEGER,
    match_reasoning TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    notified INTEGER DEFAULT 0
)
"""


class JobStore:
    """Lightweight SQLite-backed persistence for scraped jobs."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def open(self):
        """Open the database connection and ensure the schema exists."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute(CREATE_TABLE_SQL)
        await self._db.commit()
        logger.info(f"JobStore opened (db={self.db_path})")

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # -- Context-manager support --
    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # -- Core CRUD --

    async def job_exists(self, apply_link: str) -> bool:
        """Check whether a job has already been recorded."""
        async with self._db.execute(
            "SELECT 1 FROM jobs WHERE apply_link = ?", (apply_link,)
        ) as cursor:
            return await cursor.fetchone() is not None

    async def upsert_job(self, job: Job) -> bool:
        """
        Insert a new job or update last_seen / description / score for an existing one.
        Returns True if the job was newly inserted.
        """
        now = datetime.now(timezone.utc).isoformat()
        posted = job.posted_date.isoformat() if job.posted_date else None

        existing = await self.job_exists(job.apply_link)

        if existing:
            await self._db.execute(
                """
                UPDATE jobs
                SET last_seen = ?,
                    description = CASE WHEN ? != '' THEN ? ELSE description END,
                    match_score = COALESCE(?, match_score),
                    match_reasoning = COALESCE(?, match_reasoning),
                    location = CASE WHEN ? != '' THEN ? ELSE location END,
                    posted_date = COALESCE(?, posted_date)
                WHERE apply_link = ?
                """,
                (
                    now,
                    job.description, job.description,
                    job.match_score,
                    job.match_reasoning,
                    job.location, job.location,
                    posted,
                    job.apply_link,
                ),
            )
        else:
            await self._db.execute(
                """
                INSERT INTO jobs
                    (apply_link, title, company, location, description,
                     posted_date, match_score, match_reasoning,
                     first_seen, last_seen, notified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    job.apply_link,
                    job.title,
                    job.company,
                    job.location,
                    job.description,
                    posted,
                    job.match_score,
                    job.match_reasoning,
                    now,
                    now,
                ),
            )

        await self._db.commit()
        return not existing

    async def mark_notified(self, apply_link: str):
        """Mark a job as having been notified."""
        await self._db.execute(
            "UPDATE jobs SET notified = 1 WHERE apply_link = ?", (apply_link,)
        )
        await self._db.commit()

    async def get_unnotified_jobs(self, min_score: int = 80) -> List[Job]:
        """Return all jobs that passed the score threshold but haven't been notified."""
        rows = []
        async with self._db.execute(
            """
            SELECT * FROM jobs
            WHERE notified = 0 AND match_score >= ?
            ORDER BY match_score DESC
            """,
            (min_score,),
        ) as cursor:
            rows = await cursor.fetchall()

        jobs = []
        for row in rows:
            jobs.append(
                Job(
                    title=row["title"],
                    company=row["company"],
                    location=row["location"],
                    description=row["description"],
                    apply_link=row["apply_link"],
                    posted_date=datetime.fromisoformat(row["posted_date"]) if row["posted_date"] else None,
                    match_score=row["match_score"],
                    match_reasoning=row["match_reasoning"],
                    first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
                    notified=bool(row["notified"]),
                )
            )
        return jobs

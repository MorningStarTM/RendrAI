import uuid
from db.database import PostgresHandler


class JobHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def create(self, session_id: str):
        """Create a new job for a session. Returns generated job_id."""
        job_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO jobs (id, session_id) VALUES (%s, %s)",
            (job_id, session_id)
        )
        return job_id

    def update_status(self, job_id: str, status: str, error_msg: str = None):
        """Update job status and optionally record an error message."""
        self.execute(
            """
            UPDATE jobs
            SET status      = %s,
                error_msg   = %s,
                updated_at  = NOW()
            WHERE id = %s
            """,
            (status, error_msg, job_id)
        )

    def increment_retry(self, job_id: str):
        """Increment retry counter by 1."""
        self.execute(
            "UPDATE jobs SET retry_count = retry_count + 1, updated_at = NOW() WHERE id = %s",
            (job_id,)
        )

    def clear_error(self, job_id: str):
        """Clear error message when retrying."""
        self.execute(
            "UPDATE jobs SET error_msg = NULL, updated_at = NOW() WHERE id = %s",
            (job_id,)
        )

    # ── Read ───────────────────────────────────────────────────────

    def get_by_id(self, job_id: str):
        return self.fetchone(
            "SELECT * FROM jobs WHERE id = %s",
            (job_id,)
        )

    def get_by_session(self, session_id: str):
        """Get the job associated with a session — used by WebSocket status endpoint."""
        return self.fetchone(
            "SELECT * FROM jobs WHERE session_id = %s",
            (session_id,)
        )

    def get_status(self, job_id: str):
        """Lightweight status-only fetch — used for polling."""
        return self.fetchone(
            "SELECT id, status, retry_count, error_msg FROM jobs WHERE id = %s",
            (job_id,)
        )

    def get_by_status(self, status: str):
        """Get all jobs with a given status — useful for admin/retry queue."""
        return self.fetchall(
            "SELECT * FROM jobs WHERE status = %s ORDER BY created_at ASC",
            (status,)
        )

    def get_failed(self):
        """All failed jobs with error messages — for error monitoring."""
        return self.fetchall(
            "SELECT * FROM jobs WHERE status = 'failed' ORDER BY updated_at DESC"
        )

    def get_pending(self):
        """All jobs still waiting to be processed."""
        return self.fetchall(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at ASC"
        )

    def get_retryable(self, max_retries: int = 3):
        """Failed jobs that haven't exceeded max retry limit."""
        return self.fetchall(
            """
            SELECT * FROM jobs
            WHERE status = 'failed' AND retry_count < %s
            ORDER BY updated_at ASC
            """,
            (max_retries,)
        )

    def count_by_status(self) -> dict:
        """Count of jobs per status — for monitoring dashboard."""
        rows = self.fetchall(
            "SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status"
        )
        return {row["status"]: row["cnt"] for row in rows} if rows else {}
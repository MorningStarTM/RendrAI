import uuid
from db.database import PostgresHandler


class SessionHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def create(self, brief_id: str, user_id: str):
        """Create a new session for a brief. Returns generated session_id."""
        session_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO sessions (id, brief_id, user_id) VALUES (%s, %s, %s)",
            (session_id, brief_id, user_id)
        )
        return session_id

    def update_status(self, session_id: str, status: str):
        """
        Update session status.
        Sets completed_at automatically when status is 'complete' or 'failed'.
        """
        self.execute(
            """
            UPDATE sessions
            SET status = %s,
                completed_at = CASE
                    WHEN %s IN ('complete', 'failed') THEN NOW()
                    ELSE completed_at
                END
            WHERE id = %s
            """,
            (status, status, session_id)
        )

    # ── Read ───────────────────────────────────────────────────────

    def get_by_id(self, session_id: str):
        return self.fetchone(
            "SELECT * FROM sessions WHERE id = %s",
            (session_id,)
        )

    def get_by_id_and_user(self, session_id: str, user_id: str):
        """Ownership-safe fetch — prevents cross-user access."""
        return self.fetchone(
            "SELECT * FROM sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id)
        )

    def get_by_brief(self, brief_id: str):
        """Get session for a given brief."""
        return self.fetchone(
            "SELECT * FROM sessions WHERE brief_id = %s",
            (brief_id,)
        )

    def get_all_by_user(self, user_id: str):
        """All sessions for a user, newest first."""
        return self.fetchall(
            "SELECT * FROM sessions WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )

    def get_by_status(self, user_id: str, status: str):
        """Filter sessions by status: pending / processing / complete / failed."""
        return self.fetchall(
            "SELECT * FROM sessions WHERE user_id = %s AND status = %s ORDER BY created_at DESC",
            (user_id, status)
        )

    def get_with_prompts(self, session_id: str, user_id: str):
        """Full session detail with all prompts — used for gallery view."""
        session = self.get_by_id_and_user(session_id, user_id)
        if not session:
            return None
        prompts = self.fetchall(
            "SELECT * FROM prompts WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )
        return {"session": dict(session), "prompts": [dict(p) for p in prompts]}

    def get_failed(self, user_id: str):
        """All failed sessions — useful for error dashboard."""
        return self.fetchall(
            "SELECT * FROM sessions WHERE user_id = %s AND status = 'failed' ORDER BY created_at DESC",
            (user_id,)
        )

    def get_duration(self, session_id: str):
        """Returns generation duration in seconds for a completed session."""
        return self.fetchone(
            """
            SELECT
                EXTRACT(EPOCH FROM (completed_at - created_at)) AS duration_seconds
            FROM sessions
            WHERE id = %s AND completed_at IS NOT NULL
            """,
            (session_id,)
        )

    def count_by_user(self, user_id: str) -> int:
        row = self.fetchone(
            "SELECT COUNT(*) AS cnt FROM sessions WHERE user_id = %s",
            (user_id,)
        )
        return row["cnt"] if row else 0

    def count_by_status(self, user_id: str) -> dict:
        """Returns count per status — used for usage dashboard."""
        rows = self.fetchall(
            """
            SELECT status, COUNT(*) AS cnt
            FROM sessions
            WHERE user_id = %s
            GROUP BY status
            """,
            (user_id,)
        )
        return {row["status"]: row["cnt"] for row in rows} if rows else {}
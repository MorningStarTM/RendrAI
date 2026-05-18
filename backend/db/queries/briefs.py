import uuid
from db.database import PostgresHandler


class BriefHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def create(self, user_id: str, content: str, source: str):
        """Insert a new brief. Returns generated brief_id."""
        brief_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO briefs (id, user_id, content, source) VALUES (%s, %s, %s, %s)",
            (brief_id, user_id, content, source)
        )
        return brief_id

    def delete(self, brief_id: str):
        self.execute(
            "DELETE FROM briefs WHERE id = %s",
            (brief_id,)
        )

    # ── Read ───────────────────────────────────────────────────────

    def get_by_id(self, brief_id: str):
        return self.fetchone(
            "SELECT * FROM briefs WHERE id = %s",
            (brief_id,)
        )

    def get_by_id_and_user(self, brief_id: str, user_id: str):
        """Ownership-safe fetch — prevents cross-user access."""
        return self.fetchone(
            "SELECT * FROM briefs WHERE id = %s AND user_id = %s",
            (brief_id, user_id)
        )

    def get_all_by_user(self, user_id: str):
        """All briefs for a user, newest first."""
        return self.fetchall(
            "SELECT * FROM briefs WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )

    def get_all_by_user_with_status(self, user_id: str):
        """Brief list with session status and prompt count — used for history view."""
        return self.fetchall(
            """
            SELECT
                b.id,
                b.content,
                b.source,
                b.created_at,
                s.id         AS session_id,
                s.status     AS session_status,
                COUNT(p.id)  AS prompt_count
            FROM briefs b
            LEFT JOIN sessions s ON s.brief_id = b.id
            LEFT JOIN prompts p  ON p.session_id = s.id
            WHERE b.user_id = %s
            GROUP BY b.id, s.id, s.status
            ORDER BY b.created_at DESC
            """,
            (user_id,)
        )

    def get_by_source(self, user_id: str, source: str):
        """Filter briefs by source type: 'csv' or 'text'."""
        return self.fetchall(
            "SELECT * FROM briefs WHERE user_id = %s AND source = %s ORDER BY created_at DESC",
            (user_id, source)
        )

    def get_recent(self, user_id: str, limit: int = 10):
        """Last N briefs for a user."""
        return self.fetchall(
            "SELECT * FROM briefs WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (user_id, limit)
        )

    def count_by_user(self, user_id: str) -> int:
        """Total briefs submitted by a user — used for stats."""
        row = self.fetchone(
            "SELECT COUNT(*) AS cnt FROM briefs WHERE user_id = %s",
            (user_id,)
        )
        return row["cnt"] if row else 0

    def count_last_hour(self, user_id: str) -> int:
        """Count briefs in last 60 minutes — used by rate limiter."""
        row = self.fetchone(
            """
            SELECT COUNT(*) AS cnt FROM briefs
            WHERE user_id = %s
            AND created_at > NOW() - INTERVAL '1 hour'
            """,
            (user_id,)
        )
        return row["cnt"] if row else 0
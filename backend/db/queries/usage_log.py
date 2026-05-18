import uuid
from db.database import PostgresHandler


class UsageLogHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def log(self, user_id: str, session_id: str, model: str,
            tokens_in: int, tokens_out: int,
            image_calls: int, cost_usd: float):
        """
        Write one usage log entry.
        Call this after every model API call (SLM, reasoning, image).
        """
        self.execute(
            """
            INSERT INTO usage_log
                (id, user_id, session_id, model,
                 tokens_in, tokens_out, image_calls, cost_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (str(uuid.uuid4()), user_id, session_id, model,
             tokens_in, tokens_out, image_calls, cost_usd)
        )

    # ── Read: session level ────────────────────────────────────────

    def get_by_session(self, session_id: str):
        """All log entries for a session — one row per model call."""
        return self.fetchall(
            "SELECT * FROM usage_log WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )

    def get_session_total(self, session_id: str):
        """Total cost and token usage for one session."""
        return self.fetchone(
            """
            SELECT
                SUM(tokens_in)   AS total_tokens_in,
                SUM(tokens_out)  AS total_tokens_out,
                SUM(image_calls) AS total_image_calls,
                SUM(cost_usd)    AS total_cost_usd
            FROM usage_log
            WHERE session_id = %s
            """,
            (session_id,)
        )

    # ── Read: user level ───────────────────────────────────────────

    def get_by_user(self, user_id: str):
        """All log entries for a user, newest first."""
        return self.fetchall(
            "SELECT * FROM usage_log WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )

    def get_user_total(self, user_id: str):
        """Lifetime totals per user — for cost dashboard."""
        return self.fetchone(
            """
            SELECT
                SUM(tokens_in)   AS total_tokens_in,
                SUM(tokens_out)  AS total_tokens_out,
                SUM(image_calls) AS total_image_calls,
                SUM(cost_usd)    AS total_cost_usd
            FROM usage_log
            WHERE user_id = %s
            """,
            (user_id,)
        )

    def get_user_total_by_model(self, user_id: str):
        """Cost breakdown per model for a user — shows which model costs most."""
        return self.fetchall(
            """
            SELECT
                model,
                SUM(tokens_in)   AS total_tokens_in,
                SUM(tokens_out)  AS total_tokens_out,
                SUM(image_calls) AS total_image_calls,
                SUM(cost_usd)    AS total_cost_usd
            FROM usage_log
            WHERE user_id = %s
            GROUP BY model
            ORDER BY total_cost_usd DESC
            """,
            (user_id,)
        )

    def get_user_daily(self, user_id: str):
        """Daily cost totals for a user — for usage graph."""
        return self.fetchall(
            """
            SELECT
                DATE(created_at) AS day,
                SUM(cost_usd)    AS total_cost_usd,
                COUNT(*)         AS total_calls
            FROM usage_log
            WHERE user_id = %s
            GROUP BY DATE(created_at)
            ORDER BY day DESC
            """,
            (user_id,)
        )

    def get_user_last_n_days(self, user_id: str, days: int = 30):
        """Cost for a user in the last N days."""
        return self.fetchone(
            """
            SELECT SUM(cost_usd) AS total_cost_usd
            FROM usage_log
            WHERE user_id = %s
            AND created_at > NOW() - INTERVAL '%s days'
            """,
            (user_id, days)
        )

    # ── Read: system level ─────────────────────────────────────────

    def get_all_users_total(self):
        """Total cost per user across the whole system — admin view."""
        return self.fetchall(
            """
            SELECT
                u.name,
                u.id AS user_id,
                SUM(ul.cost_usd) AS total_cost_usd,
                SUM(ul.image_calls) AS total_image_calls
            FROM usage_log ul
            JOIN users u ON ul.user_id = u.id
            GROUP BY u.id, u.name
            ORDER BY total_cost_usd DESC
            """
        )

    def get_system_total(self):
        """Grand total across all users — for billing overview."""
        return self.fetchone(
            """
            SELECT
                SUM(tokens_in)   AS total_tokens_in,
                SUM(tokens_out)  AS total_tokens_out,
                SUM(image_calls) AS total_image_calls,
                SUM(cost_usd)    AS total_cost_usd
            FROM usage_log
            """
        )

    def get_system_daily(self):
        """Daily system-wide cost — for ops monitoring."""
        return self.fetchall(
            """
            SELECT
                DATE(created_at) AS day,
                SUM(cost_usd)    AS total_cost_usd,
                COUNT(*)         AS total_calls
            FROM usage_log
            GROUP BY DATE(created_at)
            ORDER BY day DESC
            LIMIT 90
            """
        )
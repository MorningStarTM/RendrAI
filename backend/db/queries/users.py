import uuid
from db.database import PostgresHandler


class UserHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def create(self, name: str, token_hash: str):
        """Create a new user. Returns generated user_id."""
        user_id = str(uuid.uuid4())
        self.execute(
            "INSERT INTO users (id, name, token_hash) VALUES (%s, %s, %s)",
            (user_id, name, token_hash)
        )
        return user_id

    def deactivate(self, user_id: str):
        """Soft-delete: set active = 0."""
        self.execute(
            "UPDATE users SET active = 0 WHERE id = %s",
            (user_id,)
        )

    def reactivate(self, user_id: str):
        self.execute(
            "UPDATE users SET active = 1 WHERE id = %s",
            (user_id,)
        )

    def update_token(self, user_id: str, new_token_hash: str):
        """Rotate a user's token."""
        self.execute(
            "UPDATE users SET token_hash = %s WHERE id = %s",
            (new_token_hash, user_id)
        )

    # ── Read ───────────────────────────────────────────────────────

    def get_by_id(self, user_id: str):
        return self.fetchone(
            "SELECT * FROM users WHERE id = %s",
            (user_id,)
        )

    def get_by_token_hash(self, token_hash: str):
        """Used by auth middleware on every request."""
        return self.fetchone(
            "SELECT * FROM users WHERE token_hash = %s AND active = 1",
            (token_hash,)
        )

    def get_all_active(self):
        return self.fetchall(
            "SELECT id, name, created_at FROM users WHERE active = 1"
        )

    def get_all(self):
        return self.fetchall(
            "SELECT id, name, active, created_at FROM users ORDER BY created_at DESC"
        )

    def exists(self, user_id: str) -> bool:
        row = self.fetchone(
            "SELECT id FROM users WHERE id = %s",
            (user_id,)
        )
        return row is not None
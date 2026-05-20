import uuid
from db.database import PostgresHandler


class PromptHandler(PostgresHandler):

    # ── Write ──────────────────────────────────────────────────────

    def create(self, session_id: str, text: str, parent_id: str = None):
        """
        Insert a new prompt.
        parent_id=None for original 5 variations.
        parent_id=<id> for user-driven iterations.
        Returns generated prompt_id.
        """
        prompt_id = str(uuid.uuid4())
        self.execute(
            """
            INSERT INTO prompts (id, session_id, parent_id, text)
            VALUES (%s, %s, %s, %s)
            """,
            (prompt_id, session_id, parent_id, text)
        )
        return prompt_id

    def update_image(self, prompt_id: str, image_url: str, image_s3_key: str):
        """Set image URL and S3 key once generation completes."""
        self.execute(
            "UPDATE prompts SET image_url = %s, image_s3_key = %s WHERE id = %s",
            (image_url, image_s3_key, prompt_id)
        )

    def set_rating(self, prompt_id: str, rating: int):
        """Rate a prompt 1–5."""
        self.execute(
            "UPDATE prompts SET rating = %s WHERE id = %s",
            (rating, prompt_id)
        )

    def set_favorite(self, prompt_id: str, value: bool):
        self.execute(
            "UPDATE prompts SET is_favorite = %s WHERE id = %s",
            (1 if value else 0, prompt_id)
        )

    def set_pinned(self, prompt_id: str, value: bool):
        """Pinned prompts are excluded from S3 expiry lifecycle."""
        self.execute(
            "UPDATE prompts SET is_pinned = %s WHERE id = %s",
            (1 if value else 0, prompt_id)
        )

    # ── Read: single prompt ────────────────────────────────────────

    def get_by_id(self, prompt_id: str):
        return self.fetchone(
            "SELECT * FROM prompts WHERE id = %s",
            (prompt_id,)
        )

    def get_by_id_and_user(self, prompt_id: str, user_id: str):
        """Ownership-safe fetch — joins back to sessions to verify user."""
        return self.fetchone(
            """
            SELECT p.* FROM prompts p
            JOIN sessions s ON p.session_id = s.id
            WHERE p.id = %s AND s.user_id = %s
            """,
            (prompt_id, user_id)
        )

    # ── Read: session level ────────────────────────────────────────

    def get_by_session(self, session_id: str):
        """All prompts in a session, oldest first."""
        return self.fetchall(
            "SELECT * FROM prompts WHERE session_id = %s ORDER BY created_at ASC",
            (session_id,)
        )

    def get_roots_by_session(self, session_id: str):
        """Only the original 5 root prompts (no parent)."""
        return self.fetchall(
            """
            SELECT * FROM prompts
            WHERE session_id = %s AND parent_id IS NULL
            ORDER BY created_at ASC
            """,
            (session_id,)
        )

    def get_children(self, parent_id: str):
        """Direct children of a prompt — one level of iteration."""
        return self.fetchall(
            "SELECT * FROM prompts WHERE parent_id = %s ORDER BY created_at ASC",
            (parent_id,)
        )

    # ── Read: generation tree ──────────────────────────────────────

    def get_ancestors(self, prompt_id: str):
        """
        Walk UP the tree from prompt_id to the root.
        Returns the full ancestry chain oldest-first.
        Used to build context for the reasoning model on iteration.
        """
        return self.fetchall(
            """
            WITH RECURSIVE ancestors AS (
                SELECT * FROM prompts WHERE id = %s
                UNION ALL
                SELECT p.* FROM prompts p
                JOIN ancestors a ON p.id = a.parent_id
            )
            SELECT * FROM ancestors ORDER BY created_at ASC
            """,
            (prompt_id,)
        )

    def get_descendants(self, prompt_id: str):
        """
        Walk DOWN the tree from prompt_id.
        Returns all iterations ever made from this prompt.
        """
        return self.fetchall(
            """
            WITH RECURSIVE descendants AS (
                SELECT * FROM prompts WHERE id = %s
                UNION ALL
                SELECT p.* FROM prompts p
                JOIN descendants d ON p.parent_id = d.id
            )
            SELECT * FROM descendants ORDER BY created_at ASC
            """,
            (prompt_id,)
        )

    def get_full_tree_by_session(self, session_id: str):
        """
        Entire prompt tree for a session — all roots and all iterations.
        Frontend uses this to render the iteration history panel.
        """
        return self.fetchall(
            """
            SELECT
                p.*,
                parent.text AS parent_text
            FROM prompts p
            LEFT JOIN prompts parent ON p.parent_id = parent.id
            WHERE p.session_id = %s
            ORDER BY p.created_at ASC
            """,
            (session_id,)
        )

    # ── Read: user level ───────────────────────────────────────────

    def get_favorites_by_user(self, user_id: str):
        """All favorited images across all sessions for a user."""
        return self.fetchall(
            """
            SELECT p.*, b.content AS brief_content
            FROM prompts p
            JOIN sessions s ON p.session_id = s.id
            JOIN briefs   b ON s.brief_id   = b.id
            WHERE s.user_id = %s AND p.is_favorite = 1
            ORDER BY p.created_at DESC
            """,
            (user_id,)
        )

    def get_pinned_by_user(self, user_id: str):
        """All pinned (permanent) images for a user."""
        return self.fetchall(
            """
            SELECT p.*, b.content AS brief_content
            FROM prompts p
            JOIN sessions s ON p.session_id = s.id
            JOIN briefs   b ON s.brief_id   = b.id
            WHERE s.user_id = %s AND p.is_pinned = 1
            ORDER BY p.created_at DESC
            """,
            (user_id,)
        )

    def get_top_rated_by_user(self, user_id: str, min_rating: int = 4):
        """All prompts rated at or above a threshold for a user."""
        return self.fetchall(
            """
            SELECT p.*, b.content AS brief_content
            FROM prompts p
            JOIN sessions s ON p.session_id = s.id
            JOIN briefs   b ON s.brief_id   = b.id
            WHERE s.user_id = %s AND p.rating >= %s
            ORDER BY p.rating DESC, p.created_at DESC
            """,
            (user_id, min_rating)
        )

    def get_images_pending_upload(self):
        """Prompts that have been created but image not yet uploaded — for retry logic."""
        return self.fetchall(
            "SELECT * FROM prompts WHERE image_url IS NULL ORDER BY created_at ASC"
        )

    def count_by_session(self, session_id: str) -> int:
        row = self.fetchone(
            "SELECT COUNT(*) AS cnt FROM prompts WHERE session_id = %s",
            (session_id,)
        )
        return row["cnt"] if row else 0
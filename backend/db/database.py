import psycopg2
import psycopg2.extras
from core.config import settings

class PostgresHandler:
    def __init__(self):
        self.dsn = settings.DATABASE_URL
        # e.g. "postgresql://user:password@your-rds-endpoint:5432/dbname"

    def get_connection(self):
        conn = psycopg2.connect(self.dsn)
        return conn

    def execute(self, query: str, params: tuple = ()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor
        except Exception as e:
            conn.rollback()
            print(f"DB error: {e}")
            return None
        finally:
            conn.close()

    def fetchone(self, query: str, params: tuple = ()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            cursor.execute(query, params)
            return cursor.fetchone()
        except Exception as e:
            print(f"DB error: {e}")
            return None
        finally:
            conn.close()

    def fetchall(self, query: str, params: tuple = ()):
        conn = self.get_connection()
        try:
            cursor = conn.cursor(
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            cursor.execute(query, params)
            return cursor.fetchall()
        except Exception as e:
            print(f"DB error: {e}")
            return None
        finally:
            conn.close()

    def init_db(self, schema_path: str = "db/schema.sql"):
        from pathlib import Path
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(Path(schema_path).read_text())
            conn.commit()
            print("Database initialised")
        except Exception as e:
            conn.rollback()
            print(f"Schema init error: {e}")
        finally:
            conn.close()


            
from typing import TypedDict

import psycopg

from app.core.config import settings


class DatabaseHealth(TypedDict, total=False):
    connected: bool
    now: str
    error: str


def check_database() -> DatabaseHealth:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT now()::text AS now")
                row = cursor.fetchone()
                return {"connected": True, "now": str(row[0]) if row else ""}
    except Exception as exc:
        return {"connected": False, "error": str(exc)}

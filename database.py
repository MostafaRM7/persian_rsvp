import logging
from typing import Dict, List, Tuple
from tortoise import connections

from config import DATABASE_URL

logger = logging.getLogger("persian_rsvp.migrations")

TORTOISE_ORM = {
    "connections": {
        "default": DATABASE_URL
    },
    "apps": {
        "models": {
            "models": ["models"],
            "default_connection": "default",
        },
    },
}

# Additive schema definitions for SQLite: table -> list of (column_name, sql_definition)
SQLITE_ADDITIVE_COLUMNS: Dict[str, List[Tuple[str, str]]] = {
    "users": [
        ("pause_intensity", "REAL DEFAULT 1.0"),
        ("difficulty_tolerance", "REAL DEFAULT 0.0"),
        ("personalization_enabled", "INT DEFAULT 1"),
        ("plan_tier", "VARCHAR(20) DEFAULT 'free'"),
    ],
}



async def run_sqlite_migrations(connection_name: str = "default") -> List[str]:
    """Idempotent startup schema migration for SQLite databases.

    Inspects existing table schema using PRAGMA table_info and executes ALTER TABLE ADD COLUMN
    for any missing additive columns.
    Returns list of executed migration statements.
    """
    applied = []
    try:
        conn = connections.get(connection_name)
    except KeyError:
        return applied

    for table, columns in SQLITE_ADDITIVE_COLUMNS.items():
        try:
            _, rows = await conn.execute_query(f"PRAGMA table_info({table});")
        except Exception:
            # Table does not exist yet (e.g. before initial schema creation)
            continue

        if not rows:
            continue

        existing_cols = {row["name"] for row in rows}
        for col_name, col_def in columns:
            if col_name not in existing_cols:
                alter_sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def};"
                logger.info(f"Applying SQLite additive migration: {alter_sql}")
                print(f"[Migration] Adding missing column: {table}.{col_name} ({col_def})")
                await conn.execute_query(alter_sql)
                applied.append(f"{table}.{col_name}")

    return applied


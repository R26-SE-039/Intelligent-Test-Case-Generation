"""
Database connection, session management, and startup migration.
Uses SQLAlchemy 2.0 async engine with PostgreSQL.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import os
import uuid
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Sync URL for Alembic migrations; async URL for runtime
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:password123@localhost:5432/nextgen_qa",
)

# Neon (and other managed Postgres) require SSL and carry libpq-style params in
# the URL (?sslmode=require, &channel_binding=require) that the asyncpg driver
# does not understand. Detect that, strip those params, and enforce SSL via
# connect_args instead. Local non-SSL Postgres is unaffected.
_needs_ssl = "neon.tech" in DATABASE_URL or "sslmode=require" in DATABASE_URL
_parts = urlsplit(DATABASE_URL)
_query = [(k, v) for k, v in parse_qsl(_parts.query) if k not in ("sslmode", "channel_binding")]
_clean_url = urlunsplit((_parts.scheme, _parts.netloc, _parts.path, urlencode(_query), _parts.fragment))

# SQLAlchemy needs the asyncpg driver for async -- convert the URL scheme.
ASYNC_DATABASE_URL = _clean_url.replace("postgresql://", "postgresql+asyncpg://")

_connect_args = {"ssl": "require"} if _needs_ssl else {}
# Neon "-pooler" hosts sit behind PgBouncer (transaction pooling), where
# asyncpg's prepared-statement cache causes "prepared statement does not
# exist" errors — disable the cache on pooled endpoints.
if "-pooler" in _parts.netloc:
    _connect_args["statement_cache_size"] = 0
engine = create_async_engine(
    ASYNC_DATABASE_URL, echo=False, future=True, connect_args=_connect_args
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Create all tables on startup.
    Also runs a one-time migration to:
      1. Add new columns to existing tables if they are missing
      2. Move any orphaned user_stories / gherkin_scenarios (those without a
         project_id) into a synthetic 'Default Project' so no data is lost.
    """
    async with engine.begin() as conn:
        # ------------------------------------------------------------------
        # Step 0: Create any missing tables from the model metadata FIRST.
        # On a brand-new database (e.g. a fresh Neon instance) the ALTER
        # statements below would otherwise fail — the tables they patch only
        # pre-exist on legacy local databases. create_all skips tables that
        # already exist, so legacy databases still take the ALTER path.
        # ------------------------------------------------------------------
        from app.models import Base as ModelBase
        await conn.run_sync(ModelBase.metadata.create_all)

        # ------------------------------------------------------------------
        # Step 1: Create the projects table first (if not exists)
        # ------------------------------------------------------------------
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(200) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ
            )
        """))

        # ------------------------------------------------------------------
        # Step 2: Add project_id column to user_stories if missing
        # ------------------------------------------------------------------
        await conn.execute(text("""
            ALTER TABLE user_stories
                ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE
        """))

        # ------------------------------------------------------------------
        # Step 3: Add project_id + approved columns to gherkin_scenarios if missing
        # ------------------------------------------------------------------
        await conn.execute(text("""
            ALTER TABLE gherkin_scenarios
                ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE
        """))
        await conn.execute(text("""
            ALTER TABLE gherkin_scenarios
                ADD COLUMN IF NOT EXISTS approved BOOLEAN DEFAULT FALSE
        """))

        # ------------------------------------------------------------------
        # Step 4: Migrate orphaned rows into a "Default Project"
        # ------------------------------------------------------------------
        orphaned_stories = await conn.execute(text(
            "SELECT COUNT(*) FROM user_stories WHERE project_id IS NULL"
        ))
        orphaned_count = orphaned_stories.scalar()

        if orphaned_count and orphaned_count > 0:
            logger.info(f"Migrating {orphaned_count} orphaned user stories to 'Default Project'...")

            # Create default project if it doesn't exist
            result = await conn.execute(text(
                "SELECT id FROM projects WHERE name = 'Default Project' LIMIT 1"
            ))
            existing = result.fetchone()

            if existing:
                default_id = existing[0]
            else:
                # Generate UUID on the Python side — the id column has no
                # server-side default (SQLAlchemy uses Python uuid4()).
                new_id = str(uuid.uuid4())
                ins = await conn.execute(text(
                    "INSERT INTO projects (id, name, description) "
                    "VALUES (:id, 'Default Project', 'Auto-created during migration of existing data') "
                    "RETURNING id"
                ), {"id": new_id})
                default_id = ins.fetchone()[0]

            # Assign orphaned stories to the default project
            await conn.execute(text(
                "UPDATE user_stories SET project_id = :pid WHERE project_id IS NULL"
            ), {"pid": default_id})

            # Assign orphaned gherkin scenarios to the default project
            await conn.execute(text(
                "UPDATE gherkin_scenarios SET project_id = :pid WHERE project_id IS NULL"
            ), {"pid": default_id})

            logger.info("Migration complete — all rows are now scoped to a project.")

        # ------------------------------------------------------------------
        # Step 4.5: Upgrade user_stories primary key from (id) → (id, project_id)
        # This allows the same story ID (e.g. US-001) in multiple projects.
        # Only runs if project_id is not already part of the PK.
        # ------------------------------------------------------------------
        pk_check = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.key_column_usage
            WHERE table_name = 'user_stories'
              AND constraint_name = 'user_stories_pkey'
              AND column_name = 'project_id'
        """))
        pk_has_project_id = pk_check.scalar()

        if not pk_has_project_id:
            logger.info("Upgrading user_stories primary key to composite (id, project_id)...")
            # CASCADE also drops gherkin_scenarios_story_id_fkey which depends on the old PK
            await conn.execute(text("""
                ALTER TABLE user_stories
                    DROP CONSTRAINT user_stories_pkey CASCADE
            """))
            await conn.execute(text("""
                ALTER TABLE user_stories
                    ADD PRIMARY KEY (id, project_id)
            """))
            # Re-add the FK from gherkin_scenarios → user_stories on both columns
            await conn.execute(text("""
                ALTER TABLE gherkin_scenarios
                    ADD CONSTRAINT gherkin_scenarios_story_id_fkey
                    FOREIGN KEY (story_id, project_id)
                    REFERENCES user_stories (id, project_id)
                    ON DELETE CASCADE
            """))
            logger.info("user_stories primary key upgraded.")

        # (Step 5 removed — table creation now happens in Step 0 above.)

        # ------------------------------------------------------------------
        # Step 5.1: TestSuite versioning columns + constraint swap.
        # Existing test_suites tables had a UNIQUE(project_id, framework)
        # that destroyed prior code on regenerate. We add version/is_active/
        # selected_for_run, then swap the unique key to include version.
        # ------------------------------------------------------------------
        await conn.execute(text("""
            ALTER TABLE test_suites
                ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1
        """))
        await conn.execute(text("""
            ALTER TABLE test_suites
                ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE
        """))
        await conn.execute(text("""
            ALTER TABLE test_suites
                ADD COLUMN IF NOT EXISTS selected_for_run BOOLEAN NOT NULL DEFAULT FALSE
        """))
        await conn.execute(text("""
            ALTER TABLE test_suites
                DROP CONSTRAINT IF EXISTS uq_test_suites_project_framework
        """))
        # Add the versioned unique key only if it isn't there yet.
        constraint_exists = await conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name = 'test_suites'
              AND constraint_name = 'uq_test_suites_project_framework_version'
        """))
        if not constraint_exists.scalar():
            await conn.execute(text("""
                ALTER TABLE test_suites
                    ADD CONSTRAINT uq_test_suites_project_framework_version
                    UNIQUE (project_id, framework, version)
            """))

        # ------------------------------------------------------------------
        # Step 5.2: Auth-flow alignment — reference UUIDs from the auth
        # service (user_db). projects.organization_id and
        # user_stories.iteration_id store auth/C1 UUIDs only; the auth
        # service remains the system of record. The UNIQUE(name) constraint
        # is dropped because the project id (shared with the auth service)
        # is the real identity — different organizations may reuse names.
        # ------------------------------------------------------------------
        await conn.execute(text("""
            ALTER TABLE projects
                ADD COLUMN IF NOT EXISTS organization_id UUID
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_projects_organization_id
                ON projects (organization_id)
        """))
        await conn.execute(text("""
            ALTER TABLE projects
                DROP CONSTRAINT IF EXISTS projects_name_key
        """))
        await conn.execute(text("""
            ALTER TABLE user_stories
                ADD COLUMN IF NOT EXISTS iteration_id UUID
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_user_stories_iteration_id
                ON user_stories (iteration_id)
        """))

        # ------------------------------------------------------------------
        # Step 6: Fix stuck "processing" stories — mark as "done" if they
        # already have a Gherkin scenario generated.
        # ------------------------------------------------------------------
        await conn.execute(text("""
            UPDATE user_stories us
               SET status = 'done'
             WHERE us.status = 'processing'
               AND EXISTS (
                   SELECT 1 FROM gherkin_scenarios gs
                    WHERE gs.story_id = us.id
                      AND gs.project_id = us.project_id
               )
        """))
        logger.info("Startup migration complete.")

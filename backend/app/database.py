"""
Database connection, session management, and startup migration.
Uses SQLAlchemy 2.0 async engine with PostgreSQL.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import os
import uuid
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# Sync URL for Alembic migrations; async URL for runtime
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://admin:password123@localhost:5432/nextgen_qa",
)

# SQLAlchemy needs asyncpg driver for async — convert URL scheme
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, future=True)

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

        # ------------------------------------------------------------------
        # Step 5: Now create all remaining tables via SQLAlchemy metadata
        # ------------------------------------------------------------------
        from app.models import Base as ModelBase
        await conn.run_sync(ModelBase.metadata.create_all)

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

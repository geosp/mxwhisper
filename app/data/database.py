"""
Database connections and session management for MxWhisper
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from .models import Base

DATABASE_URL = settings.database_url
# Disable SQL echo for management scripts - set to False to reduce noise
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    """FastAPI dependency for database sessions."""
    async with async_session() as session:
        yield session


async def get_db_session():
    """Get a database session for use in activities (not as a FastAPI dependency)."""
    return async_session()


async def create_tables():
    """Create all database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
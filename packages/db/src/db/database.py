# Copyright (c) 2026 Oxara Development
# All rights reserved.
#
# This source code and any related materials are the confidential and
# proprietary information of Oxara Development.
#
# Unauthorized copying, modification, distribution, use, or disclosure
# of this software, in whole or in part, is strictly prohibited without
# prior written permission from Oxara Development.
#
# Use is restricted to authorized members of the Oxara Development team.
# Any other use requires prior written approval from Oxara Development.

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction, async_sessionmaker, create_async_engine

from .logger import logger


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning('Invalid integer for %s=%r, using default %s', name, raw, default)
        return default


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._tx: AsyncSessionTransaction | None = None

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError('UnitOfWork not entered')
        return self._session

    async def __aenter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self._tx = await self._session.begin()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._tx is None or self._session is None:
            raise RuntimeError('UnitOfWork exit without enter')

        try:
            if exc_type:
                await self._tx.rollback()
            else:
                await self._tx.commit()
        finally:
            await self._session.close()
            self._session = None
            self._tx = None


class Database:
    def __init__(self, database_url: str | None = os.getenv('DATABASE_URL')) -> None:
        self.database_url: str | None = database_url
        if not self.database_url:
            raise ValueError('DATABASE_URL environment variable is required')

        pool_size = max(1, _env_int('DB_POOL_SIZE', 30))
        max_overflow = max(0, _env_int('DB_MAX_OVERFLOW', 20))
        pool_timeout = max(5, _env_int('DB_POOL_TIMEOUT', 30))
        pool_recycle = max(30, _env_int('DB_POOL_RECYCLE', 300))

        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=True,
                pool_recycle=pool_recycle,
                pool_timeout=pool_timeout,
                pool_use_lifo=True,
                pool_logging_name='interchat.pool',
            )
            self.async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                class_=AsyncSession,
            )
            logger.info(
                'Database engine creation successful (pool_size=%s, max_overflow=%s, pool_timeout=%ss, pool_recycle=%ss)',
                pool_size,
                max_overflow,
                pool_timeout,
                pool_recycle,
            )
        except Exception as e:
            logger.error(f'Failed to create database engine: {e}')
            raise ValueError('Invalid DATABASE_URL or connection options') from e

    async def dispose(self) -> None:
        """Dispose the engine and release all pooled connections."""
        await self.engine.dispose()

    async def health_check(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text('SELECT 1'))
            return True
        except Exception as e:
            logger.error(f'Health check failed: {e}')
            return False

    def uow(self) -> UnitOfWork:
        """Return a new UnitOfWork manager for handling transactions explicitly."""
        return UnitOfWork(self.async_session)


# Global database singleton
_db: Database | None = None


def init_database(database_url: str | None = None) -> Database:
    """Initialise the global :class:`Database` singleton.

    Parameters
    ----------
    database_url:
        Connection string.  Falls back to the ``DATABASE_URL`` env-var when
        *None*.
    """
    global _db
    _db = Database(database_url)
    return _db


def get_db() -> Database:
    """Return the initialised :class:`Database` singleton.

    Raises
    ------
    RuntimeError
        If :func:`init_database` has not been called yet.
    """
    if _db is None:
        raise RuntimeError('Database not initialized. Call init_database() first.')
    return _db

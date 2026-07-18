"""Async MongoDB connection lifecycle and collection access."""

from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, IndexModel

from .config import Settings


class MongoDatabase:
    """Own the Motor client and expose the configured database."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncIOMotorClient[Any] | None = None
        self._database: AsyncIOMotorDatabase[Any] | None = None

    @property
    def database(self) -> AsyncIOMotorDatabase[Any]:
        """Return a connected Mongo database or fail with a clear message."""
        if self._database is None:
            raise RuntimeError("MongoDB has not been initialized.")
        return self._database

    async def connect(self) -> None:
        """Connect and create essential collection indexes."""
        if not self._settings.mongodb_uri:
            return
        self._client = AsyncIOMotorClient(
            self._settings.mongodb_uri,
            serverSelectionTimeoutMS=self._settings.mongodb_connect_timeout_ms,
            uuidRepresentation="standard",
        )
        await self._client.admin.command("ping")
        self._database = self._client[self._settings.mongodb_database]
        await self._create_indexes()

    async def close(self) -> None:
        """Close the active MongoDB connection."""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._database = None

    async def _create_indexes(self) -> None:
        """Create idempotent indexes required by core collections."""
        await self.database.users.create_indexes([IndexModel([("email", ASCENDING)], unique=True)])
        await self.database.projects.create_indexes([IndexModel([("owner_id", ASCENDING), ("created_at", ASCENDING)])])
        await self.database.activity_logs.create_indexes([IndexModel([("created_at", ASCENDING)])])

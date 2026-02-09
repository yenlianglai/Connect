from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.models.session import Session, SessionMessage


class SessionManager:
    def __init__(self, mongodb_url: str, db_name: str):
        self.client = AsyncIOMotorClient(mongodb_url)
        self.db = self.client[db_name]
        self.collection = self.db["sessions"]

    @staticmethod
    def format_message(role: str, content: str, timestamp: datetime | None = None) -> SessionMessage:
        """Helper to format a raw message into a SessionMessage."""
        return SessionMessage(role=role, content=content, timestamp=timestamp or datetime.now(UTC))

    async def get_session(self, session_id: str, message_limit: int | None = None) -> Session | None:
        """Retrieve a session by its ID, optionally limiting the number of messages."""
        doc = await self.collection.find_one({"_id": session_id})
        if doc:
            session = Session(**doc)
            if message_limit and len(session.messages) > message_limit:
                # Take the most recent N messages
                session.messages = session.messages[-message_limit:]
            return session
        return None

    async def create_session(self, session_id: str, metadata: dict[str, Any] | None = None) -> Session:
        """Create a new session."""
        now = datetime.now(UTC)
        session = Session(_id=session_id, messages=[], created_at=now, updated_at=now, metadata=metadata or {})
        await self.collection.insert_one(session.model_dump(by_alias=True))
        return session

    async def add_message(
        self, session_id: str, role: str, content: str, timestamp: datetime | None = None
    ) -> SessionMessage:
        """Add a message to a session and update the updated_at timestamp."""
        message = self.format_message(role, content, timestamp)
        now = datetime.now(UTC)

        # Update session: add message and update timestamp
        # Using upsert=True just in case the session doesn't exist yet
        await self.collection.update_one(
            {"_id": session_id},
            {
                "$push": {"messages": message.model_dump()},
                "$set": {"updated_at": now},
                "$setOnInsert": {"created_at": now, "metadata": {}},
            },
            upsert=True,
        )
        return message

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        result = await self.collection.delete_one({"_id": session_id})
        return result.deleted_count > 0

    async def update_metadata(self, session_id: str, metadata: dict[str, Any]):
        """Updates the metadata for an existing session."""
        await self.collection.update_one(
            {"_id": session_id}, {"$set": {"metadata": metadata, "updated_at": datetime.now(UTC)}}
        )

    async def get_all_sessions(self, limit: int = 10, skip: int = 0) -> list[Session]:
        """List sessions with pagination. Excludes documents whose _id looks like a category (cat_*)."""
        cursor = self.collection.find().skip(skip).limit(limit * 2)  # fetch extra to allow for filtering
        sessions = []
        async for doc in cursor:
            sid = doc.get("_id", "")
            if isinstance(sid, str) and sid.startswith("cat_"):
                continue  # skip category IDs stored as session docs (e.g. from mistaken UI)
            sessions.append(Session(**doc))
            if len(sessions) >= limit:
                break
        return sessions


# Singleton instance
session_manager = SessionManager(settings.MONGODB_URL, settings.MONGODB_DB_NAME)

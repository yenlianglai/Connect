import asyncio

import pytest
from testcontainers.mongodb import MongoDbContainer

from app.core.session.manager import SessionManager
from app.models.session import Session


@pytest.fixture(scope="module")
def mongodb_container():
    with MongoDbContainer("mongo:latest") as mongo:
        yield mongo


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_session_crud_flow(mongodb_container):
    # Setup manager with test container URL
    connection_url = mongodb_container.get_connection_url()
    manager = SessionManager(mongodb_url=connection_url, db_name="test_db")

    session_id = "test-session-123"

    # 1. Create Session
    session = await manager.create_session(session_id, metadata={"user_type": "beta"})
    assert session.session_id == session_id
    assert session.metadata["user_type"] == "beta"

    # 2. Add Messages
    await manager.add_message(session_id, "user", "Hello world")
    await manager.add_message(session_id, "assistant", "Hi there!")

    # 3. Retrieve and Verify
    retrieved = await manager.get_session(session_id)
    assert retrieved is not None
    assert len(retrieved.messages) == 2
    assert retrieved.messages[0].role == "user"
    assert retrieved.messages[1].role == "assistant"

    # 4. Update and Verify timestamps
    old_updated_at = retrieved.updated_at
    await asyncio.sleep(0.1)  # Ensure timestamp differs
    await manager.add_message(session_id, "user", "Next message")

    updated = await manager.get_session(session_id)
    assert len(updated.messages) == 3
    assert updated.updated_at > old_updated_at

    # 5. Delete
    deleted = await manager.delete_session(session_id)
    assert deleted is True

    final_check = await manager.get_session(session_id)
    assert final_check is None


@pytest.mark.asyncio
async def test_get_all_sessions(mongodb_container):
    connection_url = mongodb_container.get_connection_url()
    manager = SessionManager(mongodb_url=connection_url, db_name="test_db")

    # Create multiple sessions
    await manager.create_session("s1")
    await manager.create_session("s2")

    sessions = await manager.get_all_sessions()
    assert len(sessions) >= 2

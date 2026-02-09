#!/usr/bin/env python3
"""
Seed a test session that mimics learning FastAPI.
Creates a session with user/assistant messages, then resets the extraction cursor
so clicking Extract will process all messages.

Run: uv run python scripts/seed_fastapi_learning_session.py
"""

import asyncio

# Add project root to path when running as script
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.session.manager import session_manager
from app.services.memory.redis_service import redis_service

SESSION_ID = "session_fastapi_learn"
TOPIC_NAME = "Learning FastAPI"


CONVERSATION = [
    ("user", "I want to learn FastAPI. Where should I start?"),
    (
        "assistant",
        "A great place to start is the official FastAPI docs. FastAPI is a modern Python web framework "
        "built on Starlette and Pydantic. Key concepts: (1) **Routing** – use decorators like @app.get('/items') "
        "to define endpoints. (2) **Request/response models** – use Pydantic models for automatic validation and "
        "OpenAPI schema. (3) **Dependency Injection** – declare dependencies with Depends() and reuse logic across routes.",
    ),
    ("user", "How does dependency injection work in FastAPI?"),
    (
        "assistant",
        "FastAPI's dependency injection uses the `Depends()` function. You define a function (or class) that "
        "returns the value you need—e.g. get_current_user() returning a User. Then in your route you declare "
        "`user: User = Depends(get_current_user)`. FastAPI will call get_current_user, inject the result, and "
        "can reuse the same dependency in multiple routes. Dependencies can depend on other dependencies. "
        "This is great for auth, DB sessions, and shared validation.",
    ),
    ("user", "What's the difference between a Pydantic model and a plain dict for request body?"),
    (
        "assistant",
        "Using a **Pydantic model** (e.g. `class Item(BaseModel): name: str; price: float`) gives you: automatic "
        "validation (422 if invalid), type hints in the IDE, and automatic OpenAPI/JSON Schema. A **plain dict** "
        "or no body type means you get raw JSON with no validation. Best practice: define a Pydantic model for "
        "request bodies so invalid data is rejected early and your API docs stay accurate.",
    ),
    ("user", "How do I return JSON and set status codes?"),
    (
        "assistant",
        "Return a Python dict and FastAPI serializes it to JSON via jsonable_encoder. For status codes, use "
        "`Response` (e.g. `return Response(content=..., status_code=201)`) or the shorthand "
        "`raise HTTPException(status_code=404, detail='Not found')`. You can also use the `response_model` "
        "and `status_code` on the route decorator: `@app.post('/items', status_code=201)`.",
    ),
    (
        "user",
        "I heard about background tasks. When would I use them?",
    ),
    (
        "assistant",
        "Use **BackgroundTasks** when you want to do work after sending the response, without making the client wait. "
        "Examples: sending an email, writing a log, updating a cache. Add `background_tasks: BackgroundTasks` to your "
        "route, then call `background_tasks.add_task(send_email, ...)`. FastAPI runs the task after the response "
        "is sent. For heavy or long-running work, use a proper task queue (Celery, ARQ, etc.) instead.",
    ),
    ("user", "How do I run FastAPI in production?"),
    (
        "assistant",
        "Don't use `uvicorn.run(app)` directly in production. Run uvicorn as a process: "
        "`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`. Use **Gunicorn** with uvicorn workers: "
        "`gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`. Put a reverse proxy (e.g. Nginx, Caddy) "
        'in front for TLS and static files. For Docker, CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"] is common.',
    ),
]


async def main():
    print(f"Creating session: {SESSION_ID} ({TOPIC_NAME})")
    await session_manager.create_session(
        SESSION_ID,
        metadata={"topic_name": TOPIC_NAME, "source": "seed_script"},
    )

    for role, content in CONVERSATION:
        ts = datetime.now(UTC)
        await session_manager.add_message(SESSION_ID, role, content, timestamp=ts)
        print(f"  Added {role}: {content[:50]}...")

    # Reset extraction cursor so the next Extract will process all messages
    await redis_service.set_extraction_cursor(SESSION_ID, "")
    print(f"\nDone. Session has {len(CONVERSATION)} messages. Extraction cursor reset.")
    print("  In the app: select this session in the sidebar and click Extract to run extraction.")
    print(f"  Session ID: {SESSION_ID}")


if __name__ == "__main__":
    asyncio.run(main())

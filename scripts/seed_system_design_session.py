#!/usr/bin/env python3
"""
Seed a long test session: user and LLM discussing a system design problem (URL shortener).
Creates a session with many user/assistant messages, then resets the extraction cursor
so clicking Extract will process all messages.

Run: uv run python scripts/seed_system_design_session.py
"""

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.session.manager import session_manager
from app.services.memory.redis_service import redis_service

SESSION_ID = "session_system_design_url_shortener"
TOPIC_NAME = "System Design: URL Shortener"


CONVERSATION = [
    ("user", "I'd like to work through designing a URL shortener like bit.ly. Can we go step by step?"),
    (
        "assistant",
        "Sure. A URL shortener takes a long URL and returns a short alias that redirects to the original. "
        "We'll need: (1) **Core API**: encode long URL → short code, decode short code → redirect. "
        "(2) **Scale**: think read-heavy (many redirects) vs write (fewer creates). (3) **Storage**: short code → long URL mapping. "
        "Let's start with functional requirements: what should the system do from a user's perspective?",
    ),
    (
        "user",
        "Users submit a long URL and get back a short link. When someone opens the short link, they're redirected to the original URL. We need high availability and low latency for redirects.",
    ),
    (
        "assistant",
        "Good. So **functional requirements**: Create short URL from long URL; resolve short URL and redirect (302 or 301). "
        "**Non-functional**: High availability, low redirect latency (this is the hot path), and we should assume **traffic is read-heavy**—"
        "redirects vastly outnumber new short URL creations. Capacity: assume we generate millions of short URLs and billions of redirects per month. "
        "Next step is to estimate storage and bandwidth, then sketch the high-level components.",
    ),
    ("user", "How do we generate the short code? I've heard of hash functions and base62 encoding."),
    (
        "assistant",
        "Two main approaches. **(1) Hash-based**: Take the long URL, compute MD5 or SHA256, take first N characters (e.g. 7). "
        "Pros: no central counter, can be done locally. Cons: **collisions**—two URLs can hash to the same value, so you need collision handling (retry with salted hash or append sequence). "
        "**(2) Counter-based**: Use a **globally unique counter** (e.g. in a DB or distributed ID generator like Snowflake). Convert the decimal number to **base62** (a–z, A–Z, 0–9) to get a short string. "
        "Pros: no collisions, predictable length. Cons: counter is a single logical point (can be sharded by range). For 7 characters in base62 you get 62^7 ≈ 3.5 trillion unique codes.",
    ),
    ("user", "Let's go with the counter approach. How do we store the mapping?"),
    (
        "assistant",
        "We need a **key-value store** where key = short code, value = long URL (plus optional metadata: created_at, user_id, click count). "
        "**Options**: (1) **RDBMS** (e.g. PostgreSQL): simple, ACID, good for the counter and the mapping table. (2) **NoSQL** (e.g. DynamoDB, Cassandra): scale writes and partition by short code. "
        "(3) **Cache in front**: Redirects are read-heavy, so put **Redis** (or Memcached) in front of the DB. Short code → long URL in Redis; on cache miss, read from DB and populate cache. "
        "Typical design: **write path** = generate ID, store in DB (and optionally warm cache); **read path** = lookup in cache, else DB, then 302 redirect.",
    ),
    ("user", "What HTTP status code should we use for the redirect—301 or 302?"),
    (
        "assistant",
        "**302 Found (temporary redirect)**: Browser may not cache the redirect; each request hits our servers. We get **accurate click analytics** and can change the target URL later (e.g. fix typo or A/B test). "
        "**301 Moved Permanently**: Browsers and caches can cache the redirect. Fewer requests to our system, but we lose click counts and flexibility. "
        "For a URL shortener, **302** is usually preferred so we can track clicks and update destinations. Use 301 only if you explicitly want permanent, cacheable redirects and don't care about analytics.",
    ),
    ("user", "How do we make the counter highly available and avoid a single point of failure?"),
    (
        "assistant",
        "Several options. **(1) DB sequence**: PostgreSQL sequence or AUTO_INCREMENT—simple but the DB is a bottleneck for ID generation. **(2) Range-based**: Pre-allocate ranges from the DB (e.g. each app server gets 10k IDs at a time); "
        "reduces DB round-trips. **(3) Distributed ID generator**: **Snowflake-style** IDs (timestamp + machine ID + sequence) give globally unique IDs without a central DB call per request. **(4) Multiple DB replicas**: "
        "Use a sequence per replica with different offsets (e.g. replica 0: 0, 2, 4... replica 1: 1, 3, 5...) to avoid collision. For very high write throughput, Snowflake or range allocation scales better than a single DB sequence.",
    ),
    (
        "user",
        "What about duplicate long URLs? Should we return the same short link if someone shortens the same URL twice?",
    ),
    (
        "assistant",
        "**Idempotent create**: Before generating a new short code, lookup in a table keyed by long URL (or hash of long URL). If found, return the existing short URL. "
        "Storage: (long_url_hash → short_code) in a separate table or the same DB. Trade-off: saves space and keeps one short URL per long URL, but lookup-by-URL is needed on every create. "
        "Alternatively, **allow duplicates**: every create gets a new short code. Simpler, no dedup storage, but same long URL can have many short links (harder for analytics and storage). "
        "Product decision: idempotent is friendlier for sharing (everyone gets the same link for the same article).",
    ),
    ("user", "How would we scale the redirect path to billions of requests?"),
    (
        "assistant",
        "**(1) Cache aggressively**: Put **Redis (or CDN)** in front. Short code → long URL; TTL can be long (e.g. 24h or no expiry). Most redirects hit cache. **(2) Replicate cache**: Redis cluster or multiple replicas; read from replicas. "
        "**(3) DB read replicas**: Cache miss goes to a **read replica** to avoid overloading the primary. **(4) CDN**: For truly global scale, put the redirect endpoint behind a CDN; cache 302 responses at the edge (respect Cache-Control). "
        "**(5) Partition storage**: If using a NoSQL store, partition by short code so traffic is spread across nodes. Goal: majority of redirects served from cache or edge with minimal DB load.",
    ),
    ("user", "Should we store click analytics? If so, where?"),
    (
        "assistant",
        "Yes, if product needs it. **Options**: (1) **Sync in redirect path**: Increment counter in DB or cache on each redirect—simple but adds latency and load. (2) **Async**: Emit an event (e.g. to Kafka, SQS) on redirect; "
        "consumers update a **analytics store** (e.g. aggregated counts in DB, or a columnar store for detailed logs). Redirect path stays fast. (3) **Sampling**: Only log a fraction of redirects to reduce volume. "
        "For per-link click counts, a simple **async event + counter table** is common. For detailed analytics (geo, device, time series), stream events to a data pipeline and aggregate in a warehouse or OLAP store.",
    ),
    ("user", "How do we handle malicious or banned URLs?"),
    (
        "assistant",
        "**(1) Validation on create**: Check long URL against blocklists (domain blocklist, malware/phish APIs like Google Safe Browsing). Reject or flag before storing. **(2) Validation on redirect**: "
        "Before redirecting, check short code's long URL against blocklist; if banned, return 404 or a warning page instead of redirecting. **(3) Takedown**: Admin marks short code as banned; store in DB; on redirect, "
        "return 410 Gone or warning page. **(4) Rate limiting**: Limit creates per IP/user to reduce abuse. Blocklist checks can be done asynchronously after redirect to keep latency low, with a background job updating a cache of banned URLs.",
    ),
    ("user", "What's a simple data model for the DB?"),
    (
        "assistant",
        "Minimal **two-table** model. **(1) urls**: id (bigint, from counter), short_code (varchar, unique index), long_url (text), created_at, user_id (optional). **(2) id_allocator** or use DB sequence for the counter. "
        "For idempotent creates, add **(3) long_url_hash** (e.g. SHA256 of long_url) → short_code so we can lookup existing short URL by long URL. Indexes: short_code (unique, for redirect lookup), long_url_hash (for dedup). "
        "If you need click counts, add a **clicks** column to urls or a separate **analytics** table updated asynchronously.",
    ),
    ("user", "How would we do base62 encoding from a decimal ID?"),
    (
        "assistant",
        "Base62 alphabet: 0–9, a–z, A–Z (62 characters). Algorithm: take the decimal ID; repeatedly **divide by 62**, use remainder as index into alphabet; digits come out **least significant first**, so reverse the result. "
        "Example: ID 12345 → 12345 % 62 = 15 → 'f', 12345/62=199; 199%62=13 → 'd', ... Build string from remainders then reverse. Padding: for fixed-length codes (e.g. 7 chars), pad with leading zeros (or '0' in base62). "
        "Decoding: iterate characters, multiply running value by 62 and add character's index. This gives a compact, URL-safe string with no collisions if IDs are unique.",
    ),
    ("user", "What if the same user creates millions of short links? Any special design?"),
    (
        "assistant",
        "**(1) Rate limiting**: Per-user or per-API-key limits (e.g. 1000 creates/hour) to prevent abuse. **(2) Quotas**: Enforce per-user limits in the create API; return 429 when exceeded. **(3) Sharding by user_id**: "
        "If storing in a distributed DB, partition by user_id so one user's data is co-located; avoids hot partitions if you had sharded only by short_code. **(4) Analytics**: High-volume users may want bulk export or APIs—"
        "consider batch endpoints. **(5) Cost**: If IDs are from a central counter, no extra cost per user; storage and cache scale with total links. No fundamental change to the core design; mainly operational and product limits.",
    ),
    ("user", "Summary: what are the main components in our final architecture?"),
    (
        "assistant",
        "**Final high-level architecture**: (1) **API servers**: Create short URL (validate, dedup lookup, get ID from allocator, base62 encode, store, return); Redirect (lookup short code in cache/DB, return 302). "
        "(2) **ID allocator**: Distributed counter or range allocator for unique IDs. (3) **Cache (Redis)**: short_code → long_url; front the redirect path; TTL or long-lived. (4) **Primary DB**: Stores mappings, counter or ranges; "
        "read replicas for cache-miss redirects. (5) **Async pipeline** (optional): Redirect events → queue → analytics store for click counts. (6) **Blocklist / validation**: On create and optionally on redirect. "
        "**Scale**: Cache + read replicas + async analytics keep redirect latency low and create path simple.",
    ),
    ("user", "Thanks, that was a clear walkthrough. I'll try implementing a minimal version next."),
    (
        "assistant",
        "A minimal version could be: single service, DB with a sequence for IDs, one table (short_code, long_url), base62 encode the ID, and in-memory or Redis cache for redirects. Add rate limiting and blocklist later. Good luck with the implementation.",
    ),
]


async def main():
    print(f"Creating session: {SESSION_ID} ({TOPIC_NAME})")
    await session_manager.delete_session(SESSION_ID)  # Idempotent: replace if exists
    await session_manager.create_session(
        SESSION_ID,
        metadata={"topic_name": TOPIC_NAME, "source": "seed_script"},
    )

    for role, content in CONVERSATION:
        ts = datetime.now(UTC)
        await session_manager.add_message(SESSION_ID, role, content, timestamp=ts)
        preview = content[:60].replace("\n", " ") + "..." if len(content) > 60 else content
        print(f"  Added {role}: {preview}")

    await redis_service.set_extraction_cursor(SESSION_ID, "")
    print(f"\nDone. Session has {len(CONVERSATION)} messages. Extraction cursor reset.")
    print(f"  In the app: select '{TOPIC_NAME}' in the sidebar and click Extract.")
    print(f"  Session ID: {SESSION_ID}")


if __name__ == "__main__":
    asyncio.run(main())

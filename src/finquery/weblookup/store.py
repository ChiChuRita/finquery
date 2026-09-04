"""The outbound log and the lookup cache: the two tables that make the privacy claim checkable.

Both are written on their own short-lived session rather than on the caller's, for two reasons:
the log entry has to be committed **before** the request goes out (an entry that is still in a
transaction when the process dies is not a record of anything), and the categorizer calls into
here in the middle of its own uncommitted work.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from finquery.db import OutboundRequest, Profile, WebLookup

SENT = "sent"
OK = "ok"
LOG_PAGE = 50


@dataclass(frozen=True)
class Source:
    """One page a lookup relied on, as the transcript cites it."""

    url: str
    title: str

    def payload(self) -> dict[str, str]:
        return {"url": self.url, "title": self.title}


def web_lookup_enabled(session: Session, profile_id: str) -> bool:
    """The switch, read fresh: turning it off in Settings takes the next turn's tool away."""
    profile = session.get(Profile, profile_id)
    return bool(profile and profile.web_lookup_enabled)


def log_request(factory: sessionmaker[Session], profile_id: str, kind: str, target: str, token: str) -> str:
    """Record a request before it is made and return the entry's id."""
    with factory() as session:
        entry = OutboundRequest(
            profile_id=profile_id, kind=kind, target=target[:500], merchant_token=token[:120], status=SENT
        )
        session.add(entry)
        session.commit()
        return entry.id


def settle_request(factory: sessionmaker[Session], entry_id: str, status: str) -> None:
    """Say how the request ended. The entry itself was already written."""
    with factory() as session:
        entry = session.get(OutboundRequest, entry_id)
        if entry is not None:
            entry.status = status[:120]
            session.commit()


def recent_log(session: Session, profile_id: str, limit: int = LOG_PAGE) -> list[OutboundRequest]:
    """The profile's outbound log, newest first. What the Settings card lists."""
    return list(
        session.scalars(
            select(OutboundRequest)
            .where(OutboundRequest.profile_id == profile_id)
            .order_by(OutboundRequest.created_at.desc(), OutboundRequest.id)
            .limit(limit)
        ).all()
    )


def cached_lookup(factory: sessionmaker[Session], profile_id: str, token: str) -> WebLookup | None:
    """What this profile already knows about this merchant token, if anything."""
    with factory() as session:
        return session.scalars(
            select(WebLookup).where(WebLookup.profile_id == profile_id, WebLookup.merchant_token == token)
        ).one_or_none()


def store_lookup(
    factory: sessionmaker[Session],
    profile_id: str,
    token: str,
    *,
    summary: str,
    sources: Sequence[Source],
    category: str | None,
    subcategory: str | None,
    confidence: float,
    searches: int,
    fetches: int,
) -> None:
    """Keep what one lookup found, so this token never leaves this profile again."""
    with factory() as session:
        row = session.scalars(
            select(WebLookup).where(WebLookup.profile_id == profile_id, WebLookup.merchant_token == token)
        ).one_or_none()
        if row is None:
            row = WebLookup(profile_id=profile_id, merchant_token=token[:120])
            session.add(row)
        row.summary = summary[:500]
        row.sources_json = json.dumps([source.payload() for source in sources])
        row.category = category
        row.subcategory = subcategory
        row.confidence = confidence
        row.searches = searches
        row.fetches = fetches
        session.commit()


@dataclass(frozen=True)
class OutboundJournal:
    """The outbound log as the loop uses it: one entry before each request, settled after.

    It is the loop's only way to reach the outside world, which is what makes "written before
    it is sent" a property of the code rather than a promise.
    """

    factory: sessionmaker[Session]
    profile_id: str
    token: str

    def before(self, kind: str, target: str) -> str:
        return log_request(self.factory, self.profile_id, kind, target, self.token)

    def after(self, handle: str, status: str) -> None:
        settle_request(self.factory, handle, status)


def sources_of(row: WebLookup) -> list[Source]:
    return [
        Source(url=str(item["url"]), title=str(item.get("title") or item["url"]))
        for item in json.loads(row.sources_json)
    ]

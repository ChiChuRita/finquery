"""SQLite persistence.

Two families of tables. Conversations: a turn is one agent run, storing the Pydantic AI
message history (what the model sees next time) and the AI SDK UI messages (what the
transcript renders), both as JSON text, plus the memories that every conversation of a profile
shares. Data: accounts, transactions, the taxonomy, category rules and import records, plus
the outbound log and the web lookup cache of the one feature that ever talks to the internet.

Money is stored as integer cents so sums and the split constraint are exact. `transaction_view`
is what queries and charts read: it joins the names in and drops split parents so children are
never double counted.
"""

import re
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from finquery.taxonomy import DEFAULT_TAXONOMY

DEFAULT_PROFILE_NAME = "Default"
QUERY_VIEW = "transaction_view"


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profile"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    web_lookup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether a merchant token may leave this machine for a web lookup. Off by default,
    switched in Settings, and the only thing that makes the outbound log grow. See
    finquery.weblookup."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    model_slot: Mapped[str] = mapped_column(String(16), default="fast")
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    """The rolling summary of the turns that no longer fit in the prompt. Editable by the user."""
    summary_through: Mapped[int] = mapped_column(Integer, default=-1)
    """Position of the last turn the summary covers. Turns after it are sent verbatim."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    profile: Mapped[Profile] = relationship(back_populates="conversations")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Turn.position"
    )


class Turn(Base):
    __tablename__ = "turn"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    model_slot: Mapped[str] = mapped_column(String(16))
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False)
    model_messages_json: Mapped[str] = mapped_column(Text)
    ui_messages_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="turns")


class Memory(Base):
    """A durable fact, shared by every conversation of the profile. See finquery.memory."""

    __tablename__ = "memory"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(16), default="fact")
    """rule, preference or fact."""
    source: Mapped[str] = mapped_column(String(16), default="distilled")
    """explicit (the user asked to remember it) or distilled (the post-turn pass found it)."""
    created_from: Mapped[str | None] = mapped_column(ForeignKey("conversation.id", ondelete="SET NULL"), default=None)
    """The conversation the memory was established in. Null once that conversation is deleted."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OutboundRequest(Base):
    """One request that left this machine, written before it is sent. See CONTEXT.md.

    The whole privacy story is checkable from this table: `target` is literally what was sent
    (the search query or the URL) and `merchant_token` is the only thing about the household
    that any of it carries.
    """

    __tablename__ = "outbound_request"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(8))
    """search or fetch."""
    target: Mapped[str] = mapped_column(String(500))
    """The query that was searched for, or the URL that was fetched."""
    merchant_token: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(120), default="sent")
    """sent while it is in flight, then ok or a short reason it failed."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WebLookup(Base):
    """What a web lookup found about one merchant token, so it leaves at most once per profile."""

    __tablename__ = "web_lookup"
    __table_args__ = (UniqueConstraint("profile_id", "merchant_token"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    merchant_token: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(500))
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    """The pages it relied on, as a JSON list of {"url", "title"}."""
    category: Mapped[str | None] = mapped_column(String(60), default=None)
    subcategory: Mapped[str | None] = mapped_column(String(60), default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    searches: Mapped[int] = mapped_column(Integer, default=0)
    fetches: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Account(Base):
    """A bank account or card. Created by an import or by hand, unique by name per profile."""

    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("profile_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    iban: Mapped[str | None] = mapped_column(String(34), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("profile_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)

    subcategories: Mapped[list["Subcategory"]] = relationship(
        back_populates="category", cascade="all, delete-orphan", order_by="Subcategory.position"
    )


class Subcategory(Base):
    __tablename__ = "subcategory"
    __table_args__ = (UniqueConstraint("category_id", "name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    position: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category] = relationship(back_populates="subcategories")


class CategoryRule(Base):
    """A pattern the profile assigns to a category. Matching itself lands in ticket 07."""

    __tablename__ = "category_rule"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    pattern: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[str] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategory.id", ondelete="SET NULL"), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Import(Base):
    """One ingestion: the file, the mapping used and what came of it."""

    __tablename__ = "import"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    file_name: Mapped[str] = mapped_column(String(260))
    kind: Mapped[str] = mapped_column(String(16))
    preset: Mapped[str | None] = mapped_column(String(40), default=None)
    mapping_json: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    reconciliation: Mapped[str | None] = mapped_column(String(200), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Transaction(Base):
    """One booking. A transaction with children is a split parent: only its children count."""

    __tablename__ = "transaction"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"), index=True)
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    counterparty: Mapped[str | None] = mapped_column(String(200), default=None)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("category.id", ondelete="SET NULL"), default=None)
    subcategory_id: Mapped[str | None] = mapped_column(ForeignKey("subcategory.id", ondelete="SET NULL"), default=None)
    enriched_title: Mapped[str | None] = mapped_column(String(120), default=None)
    enriched_description: Mapped[str | None] = mapped_column(String(200), default=None)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    import_id: Mapped[str | None] = mapped_column(ForeignKey("import.id", ondelete="SET NULL"), default=None)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("transaction.id", ondelete="CASCADE"), default=None, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# The view every query and chart reads. It drops split parents so children are never double
# counted, and exposes euros next to cents so generated SQL can sum either.
QUERY_VIEW_SQL = f"""
CREATE VIEW {QUERY_VIEW} AS
SELECT t.id                     AS id,
       t.profile_id             AS profile_id,
       t.booked_on              AS booked_on,
       t.amount_cents           AS amount_cents,
       t.amount_cents / 100.0   AS amount,
       t.description            AS description,
       t.counterparty           AS counterparty,
       t.enriched_title         AS title,
       t.enriched_description   AS enrichment,
       c.name                   AS category,
       s.name                   AS subcategory,
       a.name                   AS account,
       t.source                 AS source,
       t.import_id              AS import_id,
       t.parent_id              AS parent_id
FROM "transaction" t
JOIN account a ON a.id = t.account_id
LEFT JOIN category c ON c.id = t.category_id
LEFT JOIN subcategory s ON s.id = t.subcategory_id
WHERE NOT EXISTS (SELECT 1 FROM "transaction" child WHERE child.parent_id = t.id)
"""


class Changeset(Base):
    """An agent-proposed mutation with an exact preview, inert until applied.

    `payload_json` is the resolved intent: every category and every row is already an id, so
    applying it is deterministic code that needs no model. `preview_json` is the affected rows
    with their before and after as they were at proposal time, which is what the card renders.
    `row_version` is a hash of those rows: if it no longer matches when Apply arrives, the data
    moved underneath and the changeset is stale rather than applied to a state nobody saw.
    """

    __tablename__ = "changeset"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL"), default=None, index=True
    )
    """The chat it was proposed in. Null for the Settings taxonomy editor, or once that chat is gone."""
    kind: Mapped[str] = mapped_column(String(16))
    """recategorize, split, edit, delete or taxonomy."""
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    """proposed, applied, discarded, stale or superseded."""
    payload_json: Mapped[str] = mapped_column(Text)
    preview_json: Mapped[str] = mapped_column(Text)
    row_version: Mapped[str] = mapped_column(String(64))
    undo_json: Mapped[str | None] = mapped_column(Text, default=None)
    """The state to restore, for the kinds an Undo can revert."""
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """Set once it ran. Still set after an undo, which is what tells that apart from a discard."""


class SplitSumError(ValueError):
    """The children of a split do not sum to their parent's amount."""


def split_sum_error(legs_cents: int, amount_cents: int) -> SplitSumError:
    """The one wording for a broken split, whether a flush found it or a proposal did."""
    return SplitSumError(
        f"The legs of the split add up to {legs_cents / 100:.2f} "
        f"but the transaction is {amount_cents / 100:.2f}."
    )


def _split_parents_touched(session: Session) -> set[str]:
    """The parents whose children may have moved in this flush.

    A newly inserted transaction only matters through its `parent_id`: it cannot have children
    yet unless those children are in the same flush, and then they name it themselves. An
    updated or deleted row can be either half of a split, so both its own id and its parent's
    are candidates. That keeps an import of thousands of rows out of the check entirely.
    """
    touched: set[str] = set()
    for obj in session.new:
        if isinstance(obj, Transaction) and obj.parent_id:
            touched.add(obj.parent_id)
    for obj in (*session.dirty, *session.deleted):
        if isinstance(obj, Transaction):
            touched.add(obj.parent_id or obj.id)
    return touched


def _enforce_split_sums(session: Session, _context: object) -> None:
    """Any transaction that has children is a split parent, and the children must sum to it.

    One guard for every writer (import, the transactions page, changesets), hung off the
    session rather than repeated in each caller. `after_flush` still sees which rows the unit of
    work touched while their INSERTs and UPDATEs are already on the connection, so a parent and
    its children written in the same transaction are checked together.
    """
    touched = _split_parents_touched(session)
    if not touched:
        return
    sums = dict(
        session.connection()
        .execute(
            select(Transaction.parent_id, func.sum(Transaction.amount_cents))
            .where(Transaction.parent_id.in_(touched))
            .group_by(Transaction.parent_id)
        )
        .all()
    )
    if not sums:
        return
    parents = session.connection().execute(
        select(Transaction.id, Transaction.amount_cents).where(Transaction.id.in_(list(sums)))
    )
    for parent_id, amount_cents in parents:
        if sums[parent_id] != amount_cents:
            raise split_sum_error(sums[parent_id], amount_cents)


_WHITESPACE = re.compile(r"\s+")


def fingerprint(account_id: str, booked_on: date, amount_cents: int, description: str) -> str:
    """Identity of a booking for duplicate detection: account, date, amount, normalized text."""
    normalized = _WHITESPACE.sub(" ", description).strip().casefold()
    return sha256(f"{account_id}|{booked_on.isoformat()}|{amount_cents}|{normalized}".encode()).hexdigest()[:32]


# Columns added to a table that already shipped. `create_all` creates tables but never alters
# them, so a database from an earlier version needs these statements or it loses its rows. A
# whole new table (`memory`) needs no entry here: create_all does create that.
# TODO: additive columns only. A change of shape needs a real versioned upgrade function.
NEW_COLUMNS: dict[str, dict[str, str]] = {
    "conversation": {
        "summary": "TEXT",
        "summary_through": "INTEGER NOT NULL DEFAULT -1",
    },
    "profile": {
        "web_lookup_enabled": "BOOLEAN NOT NULL DEFAULT 0",
    },
}


def _add_new_columns(connection: Connection) -> None:
    for table, columns in NEW_COLUMNS.items():
        existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
        if not existing:
            continue
        for column, declaration in columns.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def make_session_factory(db_path: Path | str) -> sessionmaker[Session]:
    """Create the schema if needed and return a session factory.

    Pass ":memory:" for an in-process throwaway database (tests).
    """
    if str(db_path) == ":memory:":
        url = "sqlite://"
        connect_args: dict[str, object] = {"check_same_thread": False}
        from sqlalchemy.pool import StaticPool

        engine = create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    else:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _add_new_columns(connection)
        connection.exec_driver_sql(f"DROP VIEW IF EXISTS {QUERY_VIEW}")
        connection.exec_driver_sql(QUERY_VIEW_SQL)

    factory = sessionmaker(engine, expire_on_commit=False)
    event.listen(factory, "after_flush", _enforce_split_sums)
    return factory


def create_profile(session: Session, name: str) -> Profile:
    """Create a profile with the default taxonomy already in it."""
    profile = Profile(name=name)
    session.add(profile)
    session.flush()
    for position, (category_name, subcategory_names) in enumerate(DEFAULT_TAXONOMY.items()):
        category = Category(profile_id=profile.id, name=category_name, position=position)
        category.subcategories = [
            Subcategory(profile_id=profile.id, name=subcategory_name, position=index)
            for index, subcategory_name in enumerate(subcategory_names)
        ]
        session.add(category)
    session.commit()
    return profile


def ensure_default_profile(session: Session) -> Profile:
    profile = session.query(Profile).filter_by(name=DEFAULT_PROFILE_NAME).one_or_none()
    if profile is None:
        profile = create_profile(session, DEFAULT_PROFILE_NAME)
    return profile


def ensure_account(session: Session, profile_id: str, name: str) -> Account:
    account = session.query(Account).filter_by(profile_id=profile_id, name=name).one_or_none()
    if account is None:
        account = Account(profile_id=profile_id, name=name)
        session.add(account)
        session.flush()
    return account

"""SQLite persistence: profiles, conversations and turns.

A turn is one agent run: the user message plus everything the assistant produced for it.
Each turn row stores the Pydantic AI message history (what the model sees next time) and
the AI SDK UI messages (what the transcript renders). Both are JSON text columns.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DEFAULT_PROFILE_NAME = "Default"


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversations: Mapped[list["Conversation"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    profile_id: Mapped[str] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    model_slot: Mapped[str] = mapped_column(String(16), default="fast")
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

    # TODO: create_all only; versioned upgrade functions once the first schema change lands.
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def ensure_default_profile(session: Session) -> Profile:
    profile = session.query(Profile).filter_by(name=DEFAULT_PROFILE_NAME).one_or_none()
    if profile is None:
        profile = Profile(name=DEFAULT_PROFILE_NAME)
        session.add(profile)
        session.commit()
    return profile

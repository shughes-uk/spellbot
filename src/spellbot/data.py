import json
from datetime import datetime
from pathlib import Path

import alembic
import alembic.config
import discord
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    and_,
    create_engine,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

from spellbot.constants import THUMB_URL

PACKAGE_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = PACKAGE_ROOT / "assets"
ALEMBIC_INI = ASSETS_DIR / "alembic.ini"
VERSIONS_DIR = PACKAGE_ROOT / "versions"


Base = declarative_base()


class Server(Base):
    __tablename__ = "servers"
    guild_xid = Column(BigInteger, primary_key=True, nullable=False)
    prefix = Column(String(10), nullable=False, default="!")
    expire = Column(Integer, nullable=False, server_default=text("30"))  # minutes
    games = relationship("Game", back_populates="server")
    channels = relationship("Channel", back_populates="server")

    def bot_allowed_in(self, channel_name):
        return not self.channels or any(
            channel.name == channel_name for channel in self.channels
        )

    def __repr__(self):
        return json.dumps(
            {
                "guild_xid": self.guild_xid,
                "prefix": self.prefix,
                "expire": self.expire,
                "channels": [channel.name for channel in self.channels],
            }
        )


class Channel(Base):
    __tablename__ = "authorized_channels"
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    guild_xid = Column(
        BigInteger, ForeignKey("servers.guild_xid", ondelete="CASCADE"), nullable=False
    )
    name = Column(String(100), nullable=False)
    server = relationship("Server", back_populates="channels")


games_tags = Table(
    "games_tags",
    Base.metadata,
    Column("game_id", Integer, ForeignKey("games.id", ondelete="CASCADE")),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE")),
)


class User(Base):
    __tablename__ = "users"
    xid = Column(BigInteger, primary_key=True, nullable=False)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    cached_name = Column(String(50))
    invited = Column(Boolean, server_default=text("false"), nullable=False)
    invite_confirmed = Column(Boolean, server_default=text("false"), nullable=False)
    game = relationship("Game", back_populates="users")

    @property
    def waiting(self):
        return self.game and self.game.status in ["pending", "ready"]


class Game(Base):
    __tablename__ = "games"
    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    size = Column(Integer, nullable=False)
    guild_xid = Column(
        BigInteger, ForeignKey("servers.guild_xid", ondelete="CASCADE"), nullable=False
    )
    channel_xid = Column(BigInteger)
    title = Column(String(255))
    status = Column(String(30), nullable=False, server_default=text("'pending'"))
    message = Column(String(255))
    message_xid = Column(BigInteger)
    users = relationship("User", back_populates="game")
    server = relationship("Server", back_populates="games")

    @classmethod
    def expired(cls, session):
        return (
            session.query(Game)
            .filter(and_(datetime.utcnow() >= Game.expires_at, Game.status != "ready"))
            .all()
        )

    def __repr__(self):
        return json.dumps(self.to_json())

    def to_json(self):
        return {
            "id": self.id,
            "created_at": str(self.created_at),
            "updated_at": str(self.updated_at),
            "expires_at": str(self.expires_at),
            "size": self.size,
            "guild_xid": self.guild_xid,
            "channel_xid": self.channel_xid,
            "status": self.status,
            "message": self.message,
            "message_xid": self.message_xid,
            "title": self.title,
        }

    def to_embed(self):
        if self.status == "started":
            f"{self.title} **Your game is ready!**"
        else:
            remaining = self.size - len(self.users)
            plural = "s" if remaining > 1 else ""
            title = f"**Waiting for {remaining} more player{plural} to join...**"
        embed = discord.Embed(title=title)
        embed.set_thumbnail(url=THUMB_URL)
        embed.description = "To join/leave this game, react with ➕/➖."
        if self.users:
            players = ", ".join(sorted([f"<@{user.xid}>" for user in self.users]))
            embed.add_field(name="Players", value=players)
        embed.color = discord.Color(0x5A3EFD)
        return embed


def create_all(connection, db_url):
    config = alembic.config.Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(VERSIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    config.attributes["connection"] = connection
    alembic.command.upgrade(config, "head")


def reverse_all(connection, db_url):
    config = alembic.config.Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(VERSIONS_DIR))
    config.set_main_option("sqlalchemy.url", db_url)
    config.attributes["connection"] = connection
    alembic.command.downgrade(config, "base")


class Data:
    """Persistent and in-memory store for user data."""

    def __init__(self, db_url):
        self.db_url = db_url
        self.engine = create_engine(db_url, echo=False)
        self.conn = self.engine.connect()
        create_all(self.conn, db_url)
        self.Session = sessionmaker(bind=self.engine)
        self.metadata = Base.metadata

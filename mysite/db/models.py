from typing import Optional, List
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, SmallInteger, ForeignKey, Enum, DateTime, func, Text, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import UniqueConstraint
from .database import Base

class UserRole(str, PyEnum):
    player = 'player'
    admin = 'admin'

class UserProfile(Base):
    __tablename__ = 'user_profile'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(50), unique=True)
    age: Mapped[int] = mapped_column(SmallInteger, default=0)
    profile_image: Mapped[Optional[str]] = mapped_column(String)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.player)
    password: Mapped[str] = mapped_column(String)

    profile: Mapped[Optional['UserStatistic']] = relationship(
        'UserStatistic', back_populates='user', uselist=False, cascade='all, delete-orphan'
    )

    room_owner: Mapped[list['Room']] = relationship('Room', back_populates='owner', cascade='all, delete-orphan')
    room_memberships: Mapped[list['RoomPlayer']] = relationship('RoomPlayer', back_populates='user', cascade='all, delete-orphan')
    reviews: Mapped[list['Review']] = relationship('Review', back_populates='user', cascade='all, delete-orphan')
    game_participations: Mapped[list['GamePlayer']] = relationship('GamePlayer', back_populates='user', cascade='all, delete-orphan')
    achievements: Mapped[list['UserAchievement']] = relationship('UserAchievement', back_populates='user', cascade='all, delete-orphan')
    refresh_token: Mapped[List['RefreshToken']] = relationship('RefreshToken', back_populates='user', cascade='all, delete-orphan')
    group: Mapped[List['Group']] = relationship(back_populates='group_member', cascade='all, delete-orphan')
    chatgroup: Mapped[List['Chatgroup']] = relationship(back_populates='group_user', cascade='all, delete-orphan')

class RefreshToken(Base):
    __tablename__ = 'refresh_token'

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    token: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='refresh_token')

class UserStatistic(Base):
    __tablename__ = 'user_statistics'

    id: Mapped[int] = mapped_column(Integer, autoincrement=True, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'), unique=True)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    total_game_time: Mapped[float] = mapped_column(Float, default=0)
    mafia_games: Mapped[int] = mapped_column(Integer, default=0)
    citizen_games: Mapped[int] = mapped_column(Integer, default=0)
    detective_games: Mapped[int] = mapped_column(Integer, default=0)
    doctor_games: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='profile')

class RoomStatus(str, PyEnum):
    WAITING = "WAITING"
    STARTING = "STARTING"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"


class Room(Base):
    __tablename__ = 'room'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    room_name: Mapped[str] = mapped_column(String(100))
    max_players: Mapped[int] = mapped_column(SmallInteger)
    age: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[RoomStatus] = mapped_column(Enum(RoomStatus), default=RoomStatus.WAITING)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("user_profile.id"))

    owner: Mapped["UserProfile"] = relationship(back_populates="room_owner")
    players: Mapped[List["RoomPlayer"]] = relationship(back_populates="room", cascade="all, delete-orphan")

    reviews: Mapped[list['Review']] = relationship(back_populates='room', cascade='all, delete-orphan')

    game: Mapped[Optional['Game']] = relationship(back_populates='room', uselist=False, cascade='all, delete-orphan')

class RoomPlayer(Base):
    __tablename__ = 'room_player'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profile.id"))

    room: Mapped["Room"] = relationship(back_populates="players")
    user: Mapped["UserProfile"] = relationship(back_populates="room_memberships")

class Review(Base):
    __tablename__ = 'review'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_profile.id"))
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"))
    text: Mapped[Optional[str]] = mapped_column(Text)
    stars: Mapped[int] = mapped_column(SmallInteger)

    user: Mapped["UserProfile"] = relationship(back_populates="reviews")
    room: Mapped["Room"] = relationship(back_populates="reviews")


class GameRole(str, PyEnum):
    mafia = 'mafia'
    doctor = 'doctor'
    commissar = 'commissar'
    civilian = 'civilian'


class GamePhase(str, PyEnum):
    NIGHT = "NIGHT"
    DAY = "DAY"
    VOTING = "VOTING"


class GameWinner(str, PyEnum):
    MAFIA = "MAFIA"
    CITIZENS = "CITIZENS"


class EliminationReason(str, PyEnum):
    NIGHT_KILL = "NIGHT_KILL"
    VOTE = "VOTE"


class NightActionType(str, PyEnum):
    KILL = "KILL"
    HEAL = "HEAL"
    CHECK = "CHECK"


class AchievementCode(str, PyEnum):
    FIRST_WIN = "FIRST_WIN"
    MAFIA_MASTERMIND = "MAFIA_MASTERMIND"
    GUARDIAN_ANGEL = "GUARDIAN_ANGEL"
    SHERLOCK = "SHERLOCK"
    SURVIVOR = "SURVIVOR"
    PERFECT_TOWN = "PERFECT_TOWN"


class Game(Base):
    __tablename__ = 'game'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey('room.id'), unique=True)

    current_round: Mapped[int] = mapped_column(Integer, default=0)
    current_phase: Mapped[Optional[GamePhase]] = mapped_column(Enum(GamePhase), nullable=True)
    winner: Mapped[Optional[GameWinner]] = mapped_column(Enum(GameWinner), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    room: Mapped["Room"] = relationship(back_populates="game")
    players: Mapped[List["GamePlayer"]] = relationship(back_populates="game", cascade="all, delete-orphan")
    rounds: Mapped[List["GameRound"]] = relationship(back_populates="game", cascade="all, delete-orphan")


class GamePlayer(Base):
    __tablename__ = 'game_player'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey('game.id'))
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))

    role: Mapped[GameRole] = mapped_column(Enum(GameRole))
    is_alive: Mapped[bool] = mapped_column(Boolean, default=True)
    eliminated_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eliminated_reason: Mapped[Optional[EliminationReason]] = mapped_column(Enum(EliminationReason), nullable=True)

    game: Mapped["Game"] = relationship(back_populates="players")
    user: Mapped["UserProfile"] = relationship(back_populates="game_participations")

    votes_cast: Mapped[List["Vote"]] = relationship(
        foreign_keys="[Vote.voter_id]", back_populates="voter", cascade="all, delete-orphan"
    )
    votes_received: Mapped[List["Vote"]] = relationship(
        foreign_keys="[Vote.target_id]", back_populates="target"
    )
    night_actions: Mapped[List["NightAction"]] = relationship(
        foreign_keys="[NightAction.actor_id]", back_populates="actor", cascade="all, delete-orphan"
    )

    has_sent_last_words: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint('game_id', 'user_id', name='uq_game_player_user'),)


class GameRound(Base):
    __tablename__ = 'game_round'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey('game.id'))
    round_number: Mapped[int] = mapped_column(Integer)

    killed_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey('game_player.id'), nullable=True)
    saved_by_doctor: Mapped[bool] = mapped_column(Boolean, default=False)
    eliminated_player_id: Mapped[Optional[int]] = mapped_column(ForeignKey('game_player.id'), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    game: Mapped["Game"] = relationship(back_populates="rounds")
    night_actions: Mapped[List["NightAction"]] = relationship(back_populates="round", cascade="all, delete-orphan")
    votes: Mapped[List["Vote"]] = relationship(back_populates="round", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint('game_id', 'round_number', name='uq_game_round_number'),)


class NightAction(Base):
    __tablename__ = 'night_action'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey('game_round.id'))
    actor_id: Mapped[int] = mapped_column(ForeignKey('game_player.id'))
    target_id: Mapped[int] = mapped_column(ForeignKey('game_player.id'))
    action_type: Mapped[NightActionType] = mapped_column(Enum(NightActionType))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    round: Mapped["GameRound"] = relationship(back_populates="night_actions")
    actor: Mapped["GamePlayer"] = relationship(foreign_keys=[actor_id], back_populates="night_actions")
    target: Mapped["GamePlayer"] = relationship(foreign_keys=[target_id])


class Vote(Base):
    __tablename__ = 'vote'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(ForeignKey('game_round.id'))
    voter_id: Mapped[int] = mapped_column(ForeignKey('game_player.id'))
    target_id: Mapped[int] = mapped_column(ForeignKey('game_player.id'))

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    round: Mapped["GameRound"] = relationship(back_populates="votes")
    voter: Mapped["GamePlayer"] = relationship(foreign_keys=[voter_id], back_populates="votes_cast")
    target: Mapped["GamePlayer"] = relationship(foreign_keys=[target_id], back_populates="votes_received")

    __table_args__ = (UniqueConstraint('round_id', 'voter_id', name='uq_vote_round_voter'),)


class Achievement(Base):
    __tablename__ = 'achievement'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[AchievementCode] = mapped_column(Enum(AchievementCode), unique=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))

    users: Mapped[List["UserAchievement"]] = relationship(back_populates="achievement", cascade="all, delete-orphan")


class UserAchievement(Base):
    __tablename__ = 'user_achievement'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    achievement_id: Mapped[int] = mapped_column(ForeignKey('achievement.id'))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["UserProfile"] = relationship(back_populates="achievements")
    achievement: Mapped["Achievement"] = relationship(back_populates="users")

    __table_args__ = (UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),)

class Group(Base):
    __tablename__ = 'group'
    id: Mapped[int ] = mapped_column(primary_key=True, autoincrement=True)
    member_id: Mapped[int ] = mapped_column(ForeignKey('user_profile.id'))

    group_name: Mapped[str] = mapped_column(String(30))
    group_image: Mapped[str|None] = mapped_column(String)

    group_member: Mapped['UserProfile'] = relationship('UserProfile', back_populates='group')

    chatgroup: Mapped[List['Chatgroup']] = relationship(back_populates='group', cascade='all, delete-orphan')


class Chatgroup(Base):
    __tablename__ = 'chat_group'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('user_profile.id'))
    group_id: Mapped[int] = mapped_column(ForeignKey('group.id'))

    text: Mapped[str|None] = mapped_column(String)
    image: Mapped[str|None] = mapped_column(String)
    video: Mapped[str|None] = mapped_column(String)
    voice: Mapped[str|None] = mapped_column(String)

    group_user: Mapped['UserProfile'] = relationship('UserProfile', back_populates='chatgroup')
    group: Mapped['Group'] = relationship('Group', back_populates='chatgroup')
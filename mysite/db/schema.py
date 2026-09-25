from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from .models import UserRole, RoomStatus, GameRole, GamePhase, GameWinner, EliminationReason, NightActionType, AchievementCode


class UserProfileSchema(BaseModel):
    username:str
    email: EmailStr
    age:int
    profile_image:Optional[str]
    role: UserRole
    password: str

class UserProfileUpdateSchema(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    age: Optional[int] = None
    profile_image: Optional[str] = None
    password: Optional[str] = None

class UserProfileListSchema(BaseModel):
    id: int
    username: str
    profile_image: Optional[str]
    role: UserRole

class UserProfileDetailSchema(BaseModel):
    id: int
    username: str
    email: EmailStr
    age: int
    profile_image: Optional[str]
    role: UserRole

class UserStatisticDetailSchema(BaseModel):
    user_id: int
    username: str
    wins: int
    games_played: int

class UserStatisticListSchema(BaseModel):
    user_id: int
    username: str


class LoginSchema(BaseModel):
    username:str
    password:str

class UserStatisticSchema(BaseModel):
    user_id: int
    games_played: int
    wins: int
    losses: int
    total_game_time: float
    mafia_games: int
    citizen_games: int
    detective_games: int
    doctor_games: int


class RoomCreateSchema(BaseModel):
    room_name: str
    max_players: int
    age: int
    owner_id: int

    mafia_count: int = 1
    doctor_count: int = 1
    commissar_count: int = 1

    day_time: int = 60
    night_time: int = 60

class RoomUpdateSchema(BaseModel):
    room_name: Optional[str] = None
    age: Optional[int] = None
    max_players: Optional[int] = None
    status: Optional[RoomStatus] = None

    mafia_count: Optional[int] = None
    doctor_count: Optional[int] = None
    commissar_count: Optional[int] = None

    day_time: Optional[int] = None
    night_time: Optional[int] = None

class RoomListSchema(BaseModel):
    id: int
    room_name: str
    max_players: int
    age: int
    status: RoomStatus
    owner_id: int

    mafia_count: int
    doctor_count: int
    commissar_count: int

    day_time: int
    night_time: int

class RoomDetailSchema(BaseModel):
    id: int
    room_name: str
    max_players: int
    age: int
    status: RoomStatus
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    owner_id: int

    mafia_count: int
    doctor_count: int
    commissar_count: int

    day_time: int
    night_time: int

class RoomPlayerCreateSchema(BaseModel):
    room_id: int
    user_id: int


class RoomPlayerListSchema(BaseModel):
    id: int
    user_id: int
    room_id: int


class RoomPlayerDetailSchema(BaseModel):
    id: int
    joined_at: datetime
    room_id: int
    user_id: int

class ReviewCreateSchema(BaseModel):
    user_id: int
    room_id: int
    text: Optional[str] = None
    stars: int


class ReviewUpdateSchema(BaseModel):
    text: Optional[str] = None
    stars: Optional[int] = None


class ReviewListSchema(BaseModel):
    id: int
    user_id: int
    stars: int

class ReviewDetailSchema(BaseModel):
    id: int
    user_id: int
    room_id: int
    text: Optional[str]
    stars: int

class GameCreateSchema(BaseModel):
    room_id: int


class GameListSchema(BaseModel):
    id: int
    room_id: int
    current_phase: Optional[GamePhase]
    winner: Optional[GameWinner]

class GameDetailSchema(BaseModel):
    id: int
    room_id: int
    current_round: int
    current_phase: Optional[GamePhase]
    winner: Optional[GameWinner]
    started_at: datetime
    finished_at: Optional[datetime]

    phase_ends_at: Optional[datetime]


class GamePlayerListSchema(BaseModel):
    id: int
    user_id: int
    role: Optional[GameRole]
    is_alive: bool

class GamePlayerDetailSchema(BaseModel):
    id: int
    game_id: int
    user_id: int
    role: Optional[GameRole]
    is_alive: bool
    eliminated_round: Optional[int]
    eliminated_reason: Optional[EliminationReason]

class GameRoundListSchema(BaseModel):
    id: int
    round_number: int
    eliminated_player_id: Optional[int]

class GameRoundDetailSchema(BaseModel):
    id: int
    game_id: int
    round_number: int
    killed_player_id: Optional[int]
    saved_by_doctor: bool
    eliminated_player_id: Optional[int]
    created_at: datetime


class NightActionCreateSchema(BaseModel):
    round_id: int
    actor_id: int
    target_id: int
    action_type: NightActionType

class NightActionDetailSchema(BaseModel):
    id: int
    round_id: int
    actor_id: int
    target_id: int
    action_type: NightActionType
    created_at: datetime
    is_mafia: Optional[bool] = None

class VoteCreateSchema(BaseModel):
    round_id: int
    voter_id: int
    target_id: int


class VoteDetailSchema(BaseModel):
    id: int
    round_id: int
    voter_id: int
    target_id: int
    created_at: datetime


class AchievementCreateSchema(BaseModel):
    code: AchievementCode
    title: str
    description: str


class AchievementUpdateSchema(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class AchievementListSchema(BaseModel):
    id: int
    code: AchievementCode
    title: str


class AchievementDetailSchema(BaseModel):
    id: int
    code: AchievementCode
    title: str
    description: str


class UserAchievementCreateSchema(BaseModel):
    user_id: int
    achievement_id: int

class UserAchievementListSchema(BaseModel):
    id: int
    achievement_id: int
    unlocked_at: datetime


class UserAchievementDetailSchema(BaseModel):
    id: int
    user_id: int
    achievement_id: int
    unlocked_at: datetime

class GroupSchema(BaseModel):
    id: int
    group_name: str
    group_image: str | None

class ChatGroupSchema(BaseModel):
    id: int
    user_id: int
    group_id: int
    text: str | None
    image: str | None
    video: str | None
    voice: str | None

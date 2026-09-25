import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from mysite.api.websocket import manager
from mysite.api.night_action import check_game_achievements
from mysite.db.database import SessionLocal
from mysite.api.dependencies import get_current_user
from mysite.db.models import UserProfile, GameRole
from mysite.db.models import (Game, GamePlayer, GameRound, NightAction, Room, Vote, RoomPlayer,
                              RoomStatus, GameRole, NightActionType, EliminationReason,)
from mysite.db.schema import (GameCreateSchema, GameListSchema, GameDetailSchema, GamePlayerListSchema,
                              GamePlayerDetailSchema, GameRoundListSchema, GameRoundDetailSchema, GamePhase, GameWinner,)

game_router = APIRouter(prefix="/game", tags=["Game"],)
game_player_router = APIRouter(prefix="/game-player", tags=["GamePlayer"],)
game_round_router = APIRouter(prefix="/game-round", tags=["GameRound"],)

MIN_PLAYERS = 4
VOTING_TIME = 30

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class GameUpdateSchema(BaseModel):
    current_round: Optional[int] = None
    winner: Optional[GameWinner] = None


def build_role_deck(
    total_players: int,
    mafia_count: int,
    doctor_count: int,
    commissar_count: int,
) -> List[GameRole]:

    special_roles_count = (mafia_count + doctor_count + commissar_count)

    if special_roles_count > total_players:
        raise HTTPException(
            status_code=400,
            detail="Количество ролей больше количества игроков",
        )

    if mafia_count < 1:
        raise HTTPException(
            status_code=400,
            detail="Количество мафии должно быть минимум 1",
        )

    deck = []

    deck.extend([GameRole.mafia] * mafia_count)

    deck.extend([GameRole.doctor] * doctor_count)

    deck.extend([GameRole.commissar] * commissar_count)

    civilian_count = (total_players - len(deck))

    deck.extend([GameRole.civilian] * civilian_count)

    random.shuffle(deck)

    return deck

@game_router.post("/create", response_model=GameDetailSchema,)
async def create_game(game_data: GameCreateSchema, db: Session = Depends(get_db),):

    room_db = (db.query(Room).filter(Room.id == game_data.room_id).first())

    if not room_db:
        raise HTTPException(
            status_code=404,
            detail="room not found",
        )

    existing_game = (db.query(Game).filter(Game.room_id == game_data.room_id).first())

    if existing_game:
        raise HTTPException(
            status_code=400,
            detail="game already exists for this room",
        )

    room_players = (db.query(RoomPlayer).filter(RoomPlayer.room_id == game_data.room_id).all())

    total_players = len(room_players)

    if total_players < MIN_PLAYERS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"need at least "
                f"{MIN_PLAYERS} players to start a game"
            ),
        )

    deck = build_role_deck(
        total_players=total_players,
        mafia_count=room_db.mafia_count,
        doctor_count=room_db.doctor_count,
        commissar_count=room_db.commissar_count,
    )

    random.shuffle(room_players)

    now = datetime.utcnow()

    game_db = Game(
        room_id=room_db.id,
        current_round=1,
        current_phase=GamePhase.NIGHT,
        started_at=now,
        phase_ends_at=(
            now
            + timedelta(
                seconds=room_db.night_time
            )
        ),
    )

    db.add(game_db)
    db.flush()

    for room_player, role in zip(
        room_players,
        deck,
    ):

        game_player = GamePlayer(
            game_id=game_db.id,
            user_id=room_player.user_id,
            role=role,
            is_alive=True,
        )

        db.add(game_player)

    game_round = GameRound(
        game_id=game_db.id,
        round_number=1,
    )

    db.add(game_round)
    room_db.status = RoomStatus.IN_PROGRESS
    room_db.started_at = now
    db.commit()
    db.refresh(game_db)

    return game_db

async def process_night(db: Session, game: Game,):

    if game.current_phase != GamePhase.NIGHT:
        return

    round_db = (
        db.query(GameRound)
        .filter(
            GameRound.game_id == game.id,
            GameRound.round_number == game.current_round,
        )
        .first()
    )

    if not round_db:

        round_db = (
            db.query(GameRound)
            .filter(
                GameRound.game_id == game.id
            )
            .order_by(
                GameRound.round_number.desc()
            )
            .first()
        )

    if not round_db:
        return

    actions = (db.query(NightAction).filter(NightAction.round_id == round_db.id).all())

    kill_action = next(
        (
            action
            for action in actions
            if action.action_type
            == NightActionType.KILL
        ),
        None,
    )

    heal_action = next(
        (
            action
            for action in actions
            if action.action_type
            == NightActionType.HEAL
        ),
        None,
    )
    killed_user_id = None

    if kill_action:

        target = (
            db.query(GamePlayer)
            .filter(
                GamePlayer.id == kill_action.target_id,

                GamePlayer.game_id == game.id,
            )
            .first()
        )

        if target and target.is_alive:

            if (
                not heal_action
                or heal_action.target_id
                != kill_action.target_id
            ):

                target.is_alive = False

                target.eliminated_round = (round_db.id)

                target.eliminated_reason = (EliminationReason.NIGHT_KILL)

                round_db.killed_player_id = (target.id)

                killed_user_id = (target.user_id)

    game.current_phase = GamePhase.DAY

    game.phase_ends_at = (datetime.utcnow() + timedelta(seconds=game.room.day_time))

    db.commit()

    await manager.broadcast(
        game.id,
        {
            "type": "phase_changed",
            "phase": game.current_phase,
            "phase_ends_at": (
                game.phase_ends_at
            ),
        },
    )

    if killed_user_id is not None:

        await manager.broadcast(
            game.id,
            {
                "type": "player_killed",
                "user_id": killed_user_id,
            },
        )

@game_router.post("/end-night/{game_id}")
async def end_night(game_id: int, db: Session = Depends(get_db),):

    game = (db.query(Game).filter(Game.id == game_id).first())

    if not game:
        raise HTTPException(
            status_code=404,
            detail="game not found",
        )

    if game.current_phase != GamePhase.NIGHT:

        raise HTTPException(
            status_code=400,
            detail="game is not in NIGHT phase",
        )

    await process_night(db, game,)

    db.refresh(game)

    round_db = (
        db.query(GameRound)
        .filter(
            GameRound.game_id == game.id,
            GameRound.round_number == game.current_round,
        )
        .first()
    )

    return {
        "message": "Night ended",
        "game_id": game.id,
        "round_id": (
            round_db.id
            if round_db
            else None
        ),

        "phase": game.current_phase,
        "phase_ends_at": (
            game.phase_ends_at
        ),

        "killed_player_id": (
            round_db.killed_player_id
            if round_db
            else None
        ),
    }

async def process_start_voting(db: Session, game: Game,):

    if game.current_phase != GamePhase.DAY:
        return

    game.current_phase = GamePhase.VOTING

    game.phase_ends_at = (
        datetime.utcnow()
        + timedelta(
            seconds=VOTING_TIME
        )
    )

    db.commit()

    await manager.broadcast(
        game.id,
        {
            "type": "phase_changed",
            "phase": game.current_phase,
            "phase_ends_at": (
                game.phase_ends_at
            ),
        },
    )

@game_router.post("/start-voting/{game_id}")
async def start_voting(game_id: int, db: Session = Depends(get_db)):

    game = (db.query(Game).filter(Game.id == game_id).first())

    if not game:
        raise HTTPException(
            status_code=404,
            detail="game not found",
        )

    if game.current_phase != GamePhase.DAY:

        raise HTTPException(
            status_code=400,
            detail="game is not in DAY phase",
        )

    await process_start_voting(db, game,)

    db.refresh(game)

    return {
        "message": "Voting started",
        "game_id": game.id,
        "round_id": game.current_round,
        "phase": game.current_phase,
        "phase_ends_at": (
            game.phase_ends_at
        ),
    }

@game_router.get("/list", response_model=List[GameListSchema])
async def list_game(db: Session = Depends(get_db)):

    return (db.query(Game).all())

@game_router.get("/detail", response_model=GameDetailSchema)
async def detail_game(game_id: int, db: Session = Depends(get_db)):

    game_db = (db.query(Game).filter(Game.id == game_id).first())

    if not game_db:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="game not found",
        )

    return game_db

@game_router.put("/update/{game_id}", response_model=GameDetailSchema)
async def update_game(game_id: int, game_data: GameUpdateSchema, db: Session = Depends(get_db)):

    game_db = (db.query(Game).filter(Game.id == game_id).first())

    if not game_db:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="game not found",
        )

    data = game_data.dict(exclude_unset=True)

    data.pop("current_phase",None,)

    for key, value in data.items():

        setattr(game_db, key, value,)

    if game_data.winner is not None:

        game_db.room.status = (RoomStatus.FINISHED)

        game_db.finished_at = (datetime.utcnow())

        game_db.phase_ends_at = None

        check_game_achievements(db, game_db.id)

    db.commit()

    db.refresh(game_db)

    if game_data.winner is not None:

        await manager.broadcast(
            game_db.id,
            {
                "type": "game_finished",
                "winner": game_db.winner,
                "phase": game_db.current_phase,
                "phase_ends_at": None,
            },
        )

    return game_db

@game_router.delete("/delete/{game_id}", response_model=dict)
async def delete_game(game_id: int, db: Session = Depends(get_db)):

    game_db = (db.query(Game).filter(Game.id == game_id).first())

    if not game_db:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="game not found",
        )

    db.delete(game_db)
    db.commit()

    return {
        "status": "success deleted"
    }

def _visible_role(viewer: GamePlayer, target: GamePlayer, game: Game) -> Optional[GameRole]:
    if game.winner is not None:
        return target.role
    if viewer.id == target.id:
        return target.role
    if not target.is_alive:
        return target.role
    if viewer.role == GameRole.mafia and target.role == GameRole.mafia:
        return target.role
    return None


@game_player_router.get("/list", response_model=List[GamePlayerListSchema])
async def list_game_player(game_id: Optional[int] = None, db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user)):

    query = db.query(GamePlayer)
    if game_id is not None:
        query = query.filter(GamePlayer.game_id == game_id)

    players = query.all()
    if not players:
        return players

    game = db.query(Game).filter(Game.id == players[0].game_id).first()
    viewer = (
        db.query(GamePlayer)
        .filter(GamePlayer.game_id == players[0].game_id, GamePlayer.user_id == current_user.id)
        .first()
    )

    result = []
    for p in players:
        visible_role = _visible_role(viewer, p, game) if viewer else (p.role if game.winner else None)
        result.append(
            GamePlayerListSchema(id=p.id, user_id=p.user_id, role=visible_role, is_alive=p.is_alive)
        )
    return result

@game_player_router.get("/detail", response_model=GamePlayerDetailSchema)
async def detail_game_player(game_player_id: int,db: Session = Depends(get_db),
    current_user: UserProfile = Depends(get_current_user)):
    target = db.query(GamePlayer).filter(GamePlayer.id == game_player_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game player not found")

    game = db.query(Game).filter(Game.id == target.game_id).first()
    viewer = (db.query(GamePlayer)
        .filter(GamePlayer.game_id == target.game_id, GamePlayer.user_id == current_user.id)
        .first())
    if not viewer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="you are not in this game")

    visible_role = _visible_role(viewer, target, game)

    return GamePlayerDetailSchema(
        id=target.id,
        game_id=target.game_id,
        user_id=target.user_id,
        role=visible_role,
        is_alive=target.is_alive,
        eliminated_round=target.eliminated_round,
        eliminated_reason=target.eliminated_reason,
    )

@game_round_router.get("/list",response_model=List[GameRoundListSchema])
async def list_game_round(game_id: Optional[int] = None, db: Session = Depends(get_db)):

    query = db.query(GameRound)
    if game_id is not None:

        query = query.filter(GameRound.game_id == game_id)

    return query.all()

@game_round_router.get("/detail",response_model=GameRoundDetailSchema)
async def detail_game_round(round_id: int, db: Session = Depends(get_db)):

    round_db = (db.query(GameRound).filter(GameRound.id == round_id).first())

    if not round_db:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="game round not found",
        )

    return round_db

async def process_voting(db: Session, game: Game):

    if game.current_phase != GamePhase.VOTING:
        return None

    round_db = (db.query(GameRound).filter(
            GameRound.game_id == game.id,
            GameRound.round_number == game.current_round,).first())

    if not round_db:
        return None

    votes = (
        db.query(Vote)
        .filter(
            Vote.round_id == round_db.id
        )
        .all()
    )

    if not votes:

        game.current_round += 1

        game.current_phase = (GamePhase.NIGHT)

        game.phase_ends_at = (
            datetime.utcnow()
            + timedelta(
                seconds=game.room.night_time
            )
        )

        new_round = GameRound(game_id=game.id, round_number=game.current_round,)

        db.add(new_round)

        db.commit()

        await manager.broadcast(
            game.id,
            {
                "type": "phase_changed",
                "phase": game.current_phase,
                "phase_ends_at": (
                    game.phase_ends_at
                ),
            },
        )

        return {
            "message": "Voting ended without votes",
            "game_id": game.id,
            "winner": None,
            "next_round": (
                game.current_round
            ),
            "phase": game.current_phase,
            "phase_ends_at": (
                game.phase_ends_at
            ),
        }

    vote_count = {}

    for vote in votes:

        vote_count[vote.target_id] = (
            vote_count.get(
                vote.target_id,
                0,
            )
            + 1
        )

    eliminated_player_id = max(vote_count,key=vote_count.get,)

    eliminated_player = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.id == eliminated_player_id,
            GamePlayer.game_id == game.id,).first())

    if not eliminated_player:
        return None

    eliminated_player.is_alive = False

    eliminated_player.eliminated_round = (round_db.id)

    eliminated_player.eliminated_reason = (EliminationReason.VOTE)

    round_db.eliminated_player_id = (eliminated_player.id)

    eliminated_user_id = (eliminated_player.user_id)

    alive_players = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game.id,
            GamePlayer.is_alive == True,
        )
        .all()
    )

    mafia_count = sum(
        1
        for player in alive_players
        if player.role == GameRole.mafia
    )

    civilian_count = sum(
        1
        for player in alive_players
        if player.role != GameRole.mafia
    )

    if mafia_count >= civilian_count:

        game.winner = (GameWinner.MAFIA)

        game.current_phase = (GamePhase.DAY)

        game.phase_ends_at = None

        game.finished_at = (datetime.utcnow())

        game.room.status = (RoomStatus.FINISHED)

        check_game_achievements(db, game.id,)

        db.commit()

        await manager.broadcast(
            game.id,
            {
                "type": "player_killed",
                "user_id": eliminated_user_id,
            },
        )

        await manager.broadcast(
            game.id,
            {
                "type": "game_finished",
                "winner": game.winner,
                "phase": game.current_phase,
                "phase_ends_at": None,
            },
        )

        return {
            "message": "Mafia wins",
            "game_id": game.id,
            "eliminated_player_id": (
                eliminated_player.id
            ),

            "winner": game.winner,
            "phase": game.current_phase,
            "phase_ends_at": None,
        }

    if mafia_count == 0:

        game.winner = (GameWinner.CITIZENS)

        game.current_phase = (GamePhase.DAY)

        game.phase_ends_at = None

        game.finished_at = (datetime.utcnow())

        game.room.status = (RoomStatus.FINISHED)

        check_game_achievements(db,game.id,)

        db.commit()

        await manager.broadcast(
            game.id,
            {
                "type": "player_killed",
                "user_id": eliminated_user_id,
            },
        )

        await manager.broadcast(
            game.id,
            {
                "type": "game_finished",
                "winner": game.winner,
                "phase": game.current_phase,
                "phase_ends_at": None,
            },
        )

        return {
            "message": "Citizens win",
            "game_id": game.id,
            "eliminated_player_id": (
                eliminated_player.id
            ),
            "winner": game.winner,
            "phase": game.current_phase,
            "phase_ends_at": None,
        }

    game.current_round += 1
    game.current_phase = (GamePhase.NIGHT)

    game.phase_ends_at = (
        datetime.utcnow()
        + timedelta(
            seconds=game.room.night_time
        )
    )

    new_round = GameRound(
        game_id=game.id,
        round_number=game.current_round,
    )

    db.add(new_round)

    db.commit()
    db.refresh(game)

    await manager.broadcast(
        game.id,
        {
            "type": "player_killed",
            "user_id": eliminated_user_id,
        },
    )

    await manager.broadcast(
        game.id,
        {
            "type": "phase_changed",
            "phase": game.current_phase,
            "phase_ends_at": (
                game.phase_ends_at
            ),
        },
    )

    return {
        "message": "Voting ended",
        "game_id": game.id,
        "eliminated_player_id": (
            eliminated_player.id
        ),

        "winner": None,
        "next_round": (
            game.current_round
        ),

        "phase": game.current_phase,
        "phase_ends_at": (
            game.phase_ends_at
        ),
    }

@game_router.post("/end-voting/{game_id}")
async def end_voting(game_id: int, db: Session = Depends(get_db)):

    game = (
        db.query(Game)
        .filter(
            Game.id == game_id
        )
        .first()
    )

    if not game:

        raise HTTPException(
            status_code=404,
            detail="game not found",
        )

    if game.current_phase != GamePhase.VOTING:

        raise HTTPException(
            status_code=400,
            detail="game is not in VOTING phase",
        )

    result = await process_voting(db, game,)

    return result

async def game_scheduler():

    while True:

        db = SessionLocal()

        try:

            games = (db.query(Game).filter(
                    Game.winner.is_(None), Game.phase_ends_at.isnot(None),).all())

            now = datetime.utcnow()

            for game in games:

                if not game.phase_ends_at:
                    continue

                if now < game.phase_ends_at:
                    continue

                if game.current_phase == GamePhase.NIGHT:

                    await process_night(db, game,)

                elif game.current_phase == GamePhase.DAY:

                    await process_start_voting(db,game,)

                elif game.current_phase == GamePhase.VOTING:

                    await process_voting(db,game,)

        except Exception as e:
            print(f"GAME SCHEDULER ERROR: {e}")
            db.rollback()

        finally:
            db.close()
        await asyncio.sleep(1)


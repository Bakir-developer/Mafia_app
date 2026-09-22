import random
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import (
    Game,
    GamePlayer,
    GameRound,
    NightAction,
    Room,
    Vote,
    RoomPlayer,
    RoomStatus,
    GameRole,
    NightActionType,
    EliminationReason
)
from mysite.db.schema import (
    GameCreateSchema,
    GameListSchema,
    GameDetailSchema,
    GamePlayerListSchema,
    GamePlayerDetailSchema,
    GameRoundListSchema,
    GameRoundDetailSchema,
)
from mysite.db.schema import GamePhase, GameWinner

game_router = APIRouter(prefix='/game', tags=['Game'])
game_player_router = APIRouter(prefix='/game-player', tags=['GamePlayer'])
game_round_router = APIRouter(prefix='/game-round', tags=['GameRound'])

MIN_PLAYERS = 4


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class GameUpdateSchema(BaseModel):
    current_round: Optional[int] = None
    current_phase: Optional[GamePhase] = None
    winner: Optional[GameWinner] = None


def build_role_deck(total_players: int) -> List[GameRole]:
    mafia_count = max(1, total_players // 4)  # ~25%
    deck = [GameRole.mafia] * mafia_count
    deck.append(GameRole.doctor)
    deck.append(GameRole.commissar)
    while len(deck) < total_players:
        deck.append(GameRole.civilian)
    return deck


@game_router.post('/create', response_model=GameDetailSchema)
async def create_game(game_data: GameCreateSchema, db: Session = Depends(get_db)):
    room_db = db.query(Room).filter(Room.id == game_data.room_id).first()
    if not room_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="room not found")

    existing_game = db.query(Game).filter(Game.room_id == game_data.room_id).first()
    if existing_game:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="game already exists for this room")

    room_players = db.query(RoomPlayer).filter(RoomPlayer.room_id == game_data.room_id).all()
    if len(room_players) < MIN_PLAYERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"need at least {MIN_PLAYERS} players to start a game",
        )

    deck = build_role_deck(len(room_players))
    random.shuffle(deck)
    random.shuffle(room_players)

    game_db = Game(room_id=game_data.room_id, current_round=1, current_phase=GamePhase.NIGHT)
    db.add(game_db)
    db.flush()

    for room_player, role in zip(room_players, deck):
        db.add(GamePlayer(
            game_id=game_db.id,
            user_id=room_player.user_id,
            role=role,
            is_alive=True
        ))

    game_round = GameRound(
        game_id=game_db.id,
        round_number=1
    )

    db.add(game_round)

    room_db.status = RoomStatus.IN_PROGRESS

    db.commit()
    db.refresh(game_db)

    return game_db

@game_router.post('/end-night/{game_id}')
async def end_night(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()

    if not game:
        raise HTTPException(status_code=404, detail="game not found")

    if game.current_phase != GamePhase.NIGHT:
        raise HTTPException(status_code=400, detail="game is not in NIGHT phase")

    round_db = (
        db.query(GameRound)
        .filter(
            GameRound.game_id == game_id,
            GameRound.round_number == game.current_round
        )
        .first()
    )

    if not round_db:
        round_db = (
            db.query(GameRound)
            .filter(GameRound.game_id == game_id)
            .order_by(GameRound.round_number.desc())
            .first()
        )

    if not round_db:
        raise HTTPException(status_code=404, detail="game round not found")

    actions = db.query(NightAction).filter(
        NightAction.round_id == round_db.id
    ).all()

    kill_action = next(
        (action for action in actions if action.action_type == NightActionType.KILL),
        None
    )

    heal_action = next(
        (action for action in actions if action.action_type == NightActionType.HEAL),
        None
    )

    if kill_action:
        target = db.query(GamePlayer).filter(
            GamePlayer.id == kill_action.target_id
        ).first()

        if target:
            if not heal_action or heal_action.target_id != kill_action.target_id:
                target.is_alive = False
                target.eliminated_round = round_db.id
                target.eliminated_reason = EliminationReason.NIGHT_KILL
                round_db.killed_player_id = target.id

    game.current_phase = GamePhase.DAY

    db.commit()

    return {
        "message": "Night ended",
        "game_id": game.id,
        "round_id": round_db.id,
        "phase": game.current_phase,
        "killed_player_id": round_db.killed_player_id
    }

@game_router.post('/start-voting/{game_id}')
async def start_voting(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()

    if not game:
        raise HTTPException(status_code=404, detail="game not found")

    if game.current_phase != GamePhase.DAY:
        raise HTTPException(
            status_code=400,
            detail="game is not in DAY phase"
        )

    game.current_phase = GamePhase.VOTING

    db.commit()
    db.refresh(game)

    return {
        "message": "Voting started",
        "game_id": game.id,
        "round_id": game.current_round,
        "phase": game.current_phase
    }

@game_router.get('/list', response_model=List[GameListSchema])
async def list_game(db: Session = Depends(get_db)):
    return db.query(Game).all()


@game_router.get('/detail', response_model=GameDetailSchema)
async def detail_game(game_id: int, db: Session = Depends(get_db)):
    game_db = db.query(Game).filter(Game.id == game_id).first()
    if not game_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game not found")
    return game_db


@game_router.put('/update/{game_id}', response_model=GameDetailSchema)
async def update_game(game_id: int, game_data: GameUpdateSchema, db: Session = Depends(get_db)):
    game_db = db.query(Game).filter(Game.id == game_id).first()
    if not game_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game not found")

    for key, value in game_data.dict(exclude_unset=True).items():
        setattr(game_db, key, value)

    if game_data.winner is not None:
        game_db.room.status = RoomStatus.FINISHED

    db.commit()
    db.refresh(game_db)
    return game_db


@game_router.delete('/delete/{game_id}', response_model=dict)
async def delete_game(game_id: int, db: Session = Depends(get_db)):
    game_db = db.query(Game).filter(Game.id == game_id).first()
    if not game_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game not found")
    db.delete(game_db)
    db.commit()
    return {'status': 'success deleted'}


@game_player_router.get('/list', response_model=List[GamePlayerListSchema])
async def list_game_player(game_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(GamePlayer)
    if game_id is not None:
        query = query.filter(GamePlayer.game_id == game_id)
    return query.all()


@game_player_router.get('/detail', response_model=GamePlayerDetailSchema)
async def detail_game_player(game_player_id: int, db: Session = Depends(get_db)):
    game_player_db = db.query(GamePlayer).filter(GamePlayer.id == game_player_id).first()
    if not game_player_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game player not found")
    return game_player_db


@game_round_router.get('/list', response_model=List[GameRoundListSchema])
async def list_game_round(game_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(GameRound)
    if game_id is not None:
        query = query.filter(GameRound.game_id == game_id)
    return query.all()


@game_round_router.get('/detail', response_model=GameRoundDetailSchema)
async def detail_game_round(round_id: int, db: Session = Depends(get_db)):
    round_db = db.query(GameRound).filter(GameRound.id == round_id).first()
    if not round_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game round not found")
    return round_db

@game_router.post('/end-voting/{game_id}')
async def end_voting(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.id == game_id).first()

    if not game:
        raise HTTPException(status_code=404, detail="game not found")

    if game.current_phase != GamePhase.VOTING:
        raise HTTPException(
            status_code=400,
            detail="game is not in VOTING phase"
        )

    round_db = (
        db.query(GameRound)
        .filter(
            GameRound.game_id == game_id,
            GameRound.round_number == game.current_round
        )
        .first()
    )

    if not round_db:
        raise HTTPException(
            status_code=404,
            detail="game round not found"
        )

    votes = db.query(Vote).filter(
        Vote.round_id == round_db.id
    ).all()

    if not votes:
        raise HTTPException(
            status_code=400,
            detail="no votes"
        )

    vote_count = {}

    for vote in votes:
        vote_count[vote.target_id] = vote_count.get(vote.target_id, 0) + 1

    eliminated_player_id = max(
        vote_count,
        key=vote_count.get
    )

    eliminated_player = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.id == eliminated_player_id,
            GamePlayer.game_id == game_id
        )
        .first()
    )

    if not eliminated_player:
        raise HTTPException(
            status_code=404,
            detail="target player not found"
        )

    eliminated_player.is_alive = False
    eliminated_player.eliminated_round = round_db.id
    eliminated_player.eliminated_reason = EliminationReason.VOTE

    round_db.eliminated_player_id = eliminated_player.id

    alive_players = db.query(GamePlayer).filter(
        GamePlayer.game_id == game_id,
        GamePlayer.is_alive == True
    ).all()

    mafia_count = sum(
        1 for player in alive_players
        if player.role == GameRole.mafia
    )

    civilian_count = sum(
        1 for player in alive_players
        if player.role != GameRole.mafia
    )

    if mafia_count >= civilian_count:
        game.winner = GameWinner.MAFIA
        game.current_phase = GamePhase.DAY
        game.room.status = RoomStatus.FINISHED

        db.commit()

        return {
            "message": "Mafia wins",
            "game_id": game.id,
            "eliminated_player_id": eliminated_player.id,
            "winner": game.winner,
            "phase": game.current_phase
        }

    if mafia_count == 0:
        game.winner = GameWinner.CITIZENS
        game.current_phase = GamePhase.DAY
        game.room.status = RoomStatus.FINISHED

        db.commit()

        return {
            "message": "Citizens win",
            "game_id": game.id,
            "eliminated_player_id": eliminated_player.id,
            "winner": game.winner,
            "phase": game.current_phase
        }

    game.current_round += 1
    game.current_phase = GamePhase.NIGHT

    new_round = GameRound(
        game_id=game.id,
        round_number=game.current_round
    )

    db.add(new_round)

    db.commit()
    db.refresh(game)

    return {
        "message": "Voting ended",
        "game_id": game.id,
        "eliminated_player_id": eliminated_player.id,
        "winner": None,
        "next_round": game.current_round,
        "phase": game.current_phase
    }
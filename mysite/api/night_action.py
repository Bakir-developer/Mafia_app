from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session

from mysite.db.database import SessionLocal
from mysite.db.models import (NightAction, Vote, Achievement, UserAchievement, GameRound, GamePlayer,
                              UserProfile, UserStatistic, AchievementCode, Game, GameWinner, GameRole, NightActionType)
from mysite.db.schema import (NightActionCreateSchema, NightActionDetailSchema, VoteCreateSchema,
                              VoteDetailSchema, AchievementCreateSchema, AchievementUpdateSchema,
                              AchievementListSchema, AchievementDetailSchema, UserAchievementListSchema, UserAchievementDetailSchema)

night_action_router = APIRouter(prefix='/night-action', tags=['NightAction'])
vote_router = APIRouter(prefix='/vote', tags=['Vote'])
achievement_router = APIRouter(prefix='/achievement', tags=['Achievement'])
user_achievement_router = APIRouter(prefix='/user-achievement', tags=['UserAchievement'])


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _check_round_and_players(db: Session, round_id: int, *player_ids: int):
    round_db = db.query(GameRound).filter(GameRound.id == round_id).first()
    if not round_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="game round not found")

    for player_id in player_ids:
        player_db = db.query(GamePlayer).filter(GamePlayer.id == player_id).first()
        if not player_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"game player {player_id} not found")
        if player_db.game_id != round_db.game_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"game player {player_id} does not belong to this game",
            )
    return round_db


@night_action_router.post('/create', response_model=NightActionDetailSchema)
async def create_night_action(action_data: NightActionCreateSchema, db: Session = Depends(get_db)):
    _check_round_and_players(db, action_data.round_id, action_data.actor_id, action_data.target_id)

    action_db = NightAction(**action_data.dict())
    db.add(action_db)
    db.commit()
    db.refresh(action_db)
    return action_db


@night_action_router.get('/list', response_model=List[NightActionDetailSchema])
async def list_night_action(round_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(NightAction)
    if round_id is not None:
        query = query.filter(NightAction.round_id == round_id)
    return query.all()


@night_action_router.get('/detail', response_model=NightActionDetailSchema)
async def detail_night_action(action_id: int, db: Session = Depends(get_db)):
    action_db = db.query(NightAction).filter(NightAction.id == action_id).first()
    if not action_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="night action not found")
    return action_db



@vote_router.post('/create', response_model=VoteDetailSchema)
async def create_vote(vote_data: VoteCreateSchema, db: Session = Depends(get_db)):
    _check_round_and_players(db, vote_data.round_id, vote_data.voter_id, vote_data.target_id)


    existing_vote = (
        db.query(Vote)
        .filter(Vote.round_id == vote_data.round_id, Vote.voter_id == vote_data.voter_id)
        .first()
    )
    if existing_vote:
        existing_vote.target_id = vote_data.target_id
        db.commit()
        db.refresh(existing_vote)
        return existing_vote

    vote_db = Vote(**vote_data.dict())
    db.add(vote_db)
    db.commit()
    db.refresh(vote_db)
    return vote_db


@vote_router.get('/list', response_model=List[VoteDetailSchema])
async def list_vote(round_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Vote)
    if round_id is not None:
        query = query.filter(Vote.round_id == round_id)
    return query.all()


@vote_router.get('/detail', response_model=VoteDetailSchema)
async def detail_vote(vote_id: int, db: Session = Depends(get_db)):
    vote_db = db.query(Vote).filter(Vote.id == vote_id).first()
    if not vote_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="vote not found")
    return vote_db


@achievement_router.post('/create', response_model=AchievementDetailSchema)
async def create_achievement(achievement_data: AchievementCreateSchema, db: Session = Depends(get_db)):
    existing = db.query(Achievement).filter(Achievement.code == achievement_data.code).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="achievement with this code already exists")

    achievement_db = Achievement(**achievement_data.dict())
    db.add(achievement_db)
    db.commit()
    db.refresh(achievement_db)
    return achievement_db


@achievement_router.get('/list', response_model=List[AchievementListSchema])
async def list_achievement(db: Session = Depends(get_db)):
    return db.query(Achievement).all()


@achievement_router.get('/detail', response_model=AchievementDetailSchema)
async def detail_achievement(achievement_id: int, db: Session = Depends(get_db)):
    achievement_db = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not achievement_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="achievement not found")
    return achievement_db


@achievement_router.put('/update/{achievement_id}', response_model=AchievementDetailSchema)
async def update_achievement(achievement_id: int, achievement_data: AchievementUpdateSchema, db: Session = Depends(get_db)):
    achievement_db = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not achievement_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="achievement not found")

    for key, value in achievement_data.dict(exclude_unset=True).items():
        setattr(achievement_db, key, value)

    db.commit()
    db.refresh(achievement_db)
    return achievement_db


@achievement_router.delete('/delete/{achievement_id}', response_model=dict)
async def delete_achievement(achievement_id: int, db: Session = Depends(get_db)):
    achievement_db = db.query(Achievement).filter(Achievement.id == achievement_id).first()
    if not achievement_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="achievement not found")
    db.delete(achievement_db)
    db.commit()
    return {'status': 'success deleted'}

def unlock_achievement(db: Session, user_id: int, achievement_code: AchievementCode):
    achievement = (db.query(Achievement).filter(Achievement.code == achievement_code).first())

    if not achievement:
        return None

    existing = (db.query(UserAchievement).filter(UserAchievement.user_id == user_id,
                                                 UserAchievement.achievement_id == achievement.id).first())

    if existing:
        return existing

    user_achievement = UserAchievement(user_id=user_id,achievement_id=achievement.id)

    db.add(user_achievement)
    db.flush()

    return user_achievement

def check_game_achievements(db: Session, game_id: int):

    game = (db.query(Game).filter(Game.id == game_id).first())

    if not game:
        return []

    if not game.winner:
        return []

    players = (db.query(GamePlayer).filter(GamePlayer.game_id == game_id).all())
    rounds = (db.query(GameRound).filter(GameRound.game_id == game_id).all())

    unlocked = []

    for player in players:

        user_id = player.user_id
        statistic = (db.query(UserStatistic).filter(UserStatistic.user_id == user_id).first())

        if statistic and statistic.wins >= 1:

            result = unlock_achievement(db, user_id, AchievementCode.FIRST_WIN)

            if result:
                unlocked.append(result)

        if (player.role == GameRole.mafia
                and game.winner == GameWinner.MAFIA):

            result = unlock_achievement(db, user_id, AchievementCode.MAFIA_MASTERMIND)

            if result:
                unlocked.append(result)

        if player.is_alive:

            result = unlock_achievement(db, user_id, AchievementCode.SURVIVOR)

            if result:
                unlocked.append(result)

        if (player.role != GameRole.mafia and player.is_alive
                and game.winner == GameWinner.CITIZENS):

            result = unlock_achievement(db, user_id, AchievementCode.PERFECT_TOWN)

            if result:
                unlocked.append(result)

        for round_db in rounds:

            if not round_db.saved_by_doctor:
                continue

            heal_action = (db.query(NightAction).filter(NightAction.round_id == round_db.id,
                    NightAction.action_type == NightActionType.HEAL).first())

            if not heal_action:
                continue

            doctor = (db.query(GamePlayer).filter(GamePlayer.id == heal_action.actor_id,
                    GamePlayer.game_id == game_id, GamePlayer.role == GameRole.doctor).first())

            if not doctor:
                continue

            result = unlock_achievement(db, doctor.user_id, AchievementCode.GUARDIAN_ANGEL)

            if result:
                unlocked.append(result)

        for round_db in rounds:

            check_actions = (db.query(NightAction).filter(NightAction.round_id == round_db.id,
                    NightAction.action_type == NightActionType.CHECK).all())

            for action in check_actions:

                commissar = (db.query(GamePlayer).filter(GamePlayer.id == action.actor_id,
                        GamePlayer.game_id == game_id, GamePlayer.role == GameRole.commissar).first())

                target = (db.query(GamePlayer).filter(GamePlayer.id == action.target_id,
                        GamePlayer.game_id == game_id).first())

                if not commissar or not target:
                    continue

                if target.role == GameRole.mafia:
                    result = unlock_achievement(db, commissar.user_id, AchievementCode.SHERLOCK)

                    if result:
                        unlocked.append(result)

    return unlocked


@user_achievement_router.get('/list', response_model=List[UserAchievementListSchema])
async def list_user_achievement(user_id: int, db: Session = Depends(get_db)):
    return db.query(UserAchievement).filter(UserAchievement.user_id == user_id).all()


@user_achievement_router.get('/detail', response_model=UserAchievementDetailSchema)
async def detail_user_achievement(user_achievement_id: int, db: Session = Depends(get_db)):
    ua_db = db.query(UserAchievement).filter(UserAchievement.id == user_achievement_id).first()
    if not ua_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user achievement not found")
    return ua_db
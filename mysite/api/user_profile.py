from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import UserProfile, UserStatistic
from mysite.db.schema import (UserProfileSchema, UserProfileListSchema, UserProfileDetailSchema)
from typing import List

user_router = APIRouter(prefix='/user', tags=['User'])

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@user_router.get('/list', response_model=List[UserProfileListSchema])
async def list_user(db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).all()
    return user_db


@user_router.get('/detail', response_model=UserProfileDetailSchema)
async def detail_user(user_id: int, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    return user_db

@user_router.put('/update')
async def update_user(user_id: int, user_data: UserProfileSchema, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    for user_key, user_value in user_data.dict().items():
        setattr(user_db, user_key, user_value)

    db.commit()
    db.refresh(user_db)
    return user_db

@user_router.delete('/delete')
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.id == user_id).first()

    if not user_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    db.delete(user_db)
    db.commit()

    return {'message': 'success deleted'}


@user_router.get('/profile/{user_id}')
async def user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter(UserProfile.id == user_id).first()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')

    statistic = db.query(UserStatistic).filter(UserStatistic.user_id == user_id).first()

    if not statistic:
        statistic = UserStatistic(user_id=user_id)
        db.add(statistic)
        db.commit()
        db.refresh(statistic)

    winrate = 0
    average_game_time = 0

    if statistic.games_played > 0:
        winrate = (statistic.wins / statistic.games_played) * 100
        average_game_time = (statistic.total_game_time / statistic.games_played)

    roles = {
        'mafia': statistic.mafia_games,
        'citizen': statistic.citizen_games,
        'detective': statistic.detective_games,
        'doctor': statistic.doctor_games
    }

    most_played_role = max(roles, key=roles.get)

    return {
        'username': user.username,
        'email': user.email,
        'age': user.age,
        'games_played': statistic.games_played,
        'wins': statistic.wins,
        'losses': statistic.losses,
        'winrate': round(winrate, 2),
        'average_game_time': round(average_game_time, 2),
        'total_game_time': statistic.total_game_time,
        'most_played_role': most_played_role
    }
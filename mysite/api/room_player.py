from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from typing import List, Optional

from mysite.db.database import SessionLocal
from mysite.db.models import RoomPlayer, Room, UserProfile
from mysite.db.schema import (RoomPlayerCreateSchema, RoomPlayerListSchema, RoomPlayerDetailSchema,)

room_player_router = APIRouter(prefix='/room-player', tags=['RoomPlayer'])

async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@room_player_router.post('/create', response_model=RoomPlayerDetailSchema)
async def create_room_player(
    room_player_data: RoomPlayerCreateSchema,
    db: Session = Depends(get_db)
):

    room = db.query(Room).filter(Room.id == room_player_data.room_id).first()

    if not room:
        raise HTTPException(
            status_code=404,
            detail="Room not found"
        )

    user = db.query(UserProfile).filter(UserProfile.id == room_player_data.user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    existing = (
        db.query(RoomPlayer)
        .filter(
            RoomPlayer.room_id == room_player_data.room_id,
            RoomPlayer.user_id == room_player_data.user_id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail="user already joined this room"
        )

    room_player_db = RoomPlayer(**room_player_data.dict())

    db.add(room_player_db)
    db.commit()
    db.refresh(room_player_db)

    return room_player_db


@room_player_router.get('/list', response_model=List[RoomPlayerListSchema])
async def list_room_player(room_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(RoomPlayer)
    if room_id is not None:
        query = query.filter(RoomPlayer.room_id == room_id)
    return query.all()


@room_player_router.get('/detail', response_model=RoomPlayerDetailSchema)
async def detail_room_player(room_player_id: int, db: Session = Depends(get_db)):
    room_player_db = db.query(RoomPlayer).filter(RoomPlayer.id == room_player_id).first()
    if not room_player_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    return room_player_db


@room_player_router.delete('/delete/{room_player_id}', response_model=dict)
async def delete_room_player(room_player_id: int, db: Session = Depends(get_db)):
    room_player_db = db.query(RoomPlayer).filter(RoomPlayer.id == room_player_id).first()
    if not room_player_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="player not found")
    db.delete(room_player_db)
    db.commit()
    return {'status': 'success deleted'}
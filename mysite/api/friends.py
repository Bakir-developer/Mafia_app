from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import UserProfile, Friend
from mysite.db.schema import FriendCreateSchema, FriendListSchema
from mysite.api.dependencies import get_current_user


friend_router = APIRouter(prefix="/friend", tags=["Friend"])


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@friend_router.post("/add")
async def add_friend(friend_data: FriendCreateSchema, db: Session = Depends(get_db),
                     current_user: UserProfile = Depends(get_current_user)):
    friend_id = friend_data.friend_id

    if current_user.id == friend_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot add yourself")

    friend_user = db.query(UserProfile).filter(UserProfile.id == friend_id).first()

    if not friend_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_friend = db.query(Friend).filter(Friend.user_id == current_user.id,
                                              Friend.friend_id == friend_id).first()

    if existing_friend:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is already your friend")

    new_friend = Friend(user_id=current_user.id, friend_id=friend_id)

    db.add(new_friend)
    db.commit()
    db.refresh(new_friend)

    return {
        "message": "Friend added successfully",
        "friend_id": friend_id
    }


@friend_router.get("/list", response_model=list[FriendListSchema])
async def get_friends(db: Session = Depends(get_db), current_user: UserProfile = Depends(get_current_user)):
    friends = db.query(Friend).filter(Friend.user_id == current_user.id).all()

    result = []

    for friendship in friends:
        friend_user = db.query(UserProfile).filter(
            UserProfile.id == friendship.friend_id).first()

        if friend_user:
            result.append({
                "id": friend_user.id,
                "username": friend_user.username,
                "profile_image": friend_user.profile_image
            })

    return result


@friend_router.delete("/delete/{friend_id}")
async def delete_friend(friend_id: int, db: Session = Depends(get_db),
                        current_user: UserProfile = Depends(get_current_user)):
    friendship = db.query(Friend).filter(Friend.user_id == current_user.id,
                                         Friend.friend_id == friend_id).first()

    if not friendship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Friend not found")

    db.delete(friendship)
    db.commit()

    return {"message": "Friend deleted successfully"}
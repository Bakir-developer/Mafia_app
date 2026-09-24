from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import UserProfile, RefreshToken, UserRole
from mysite.db.schema import UserProfileSchema, LoginSchema
from passlib.context import CryptContext
from datetime import timedelta, timezone, datetime
from typing import Optional
from pydantic import BaseModel
from mysite.config import (SECRET_KEY, ACCESS_EXPIRE_TOKEN, REFRESH_EXPIRE_TOKEN, ALGORITHM,
                           GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, FRONTEND_URL)
from jose import jwt, JWTError
from fastapi.responses import RedirectResponse
import httpx
import secrets

auth_router = APIRouter(prefix='/auth', tags=['Authorization'])
pwd_context = CryptContext(schemes='bcrypt', deprecated='auto')


class RefreshTokenSchema(BaseModel):
    refresh_token: str


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_EXPIRE_TOKEN)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict):
    return create_access_token(data=data, expires_delta=timedelta(days=REFRESH_EXPIRE_TOKEN))


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token expired or invalid'
        )


@auth_router.get('/google/login')
async def google_login():
    google_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=openid%20email%20profile"
    )
    return RedirectResponse(google_url)


@auth_router.get('/google/callback')
async def google_callback(code: str, db: Session = Depends(get_db)):

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": GOOGLE_REDIRECT_URI,
            }
        )

    token_data = token_response.json()

    if "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="Google authorization failed")

    google_access_token = token_data["access_token"]

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {google_access_token}"}
        )

    google_user = user_response.json()

    email = google_user.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Google email not found")

    user_db = db.query(UserProfile).filter(UserProfile.email == email).first()

    if not user_db:
        username = email.split("@")[0]
        original_username = username
        counter = 1

        while db.query(UserProfile).filter(UserProfile.username == username).first():
            username = f"{original_username}{counter}"
            counter += 1

        random_password = secrets.token_urlsafe(32)
        hashed_password = get_password_hash(random_password)

        user_db = UserProfile(
            username=username,
            email=email,
            age=0,
            profile_image=google_user.get("picture"),
            role=UserRole.player,
            password=hashed_password
        )

        db.add(user_db)
        db.commit()
        db.refresh(user_db)

    access_token = create_access_token({"sub": user_db.username, "user_id": user_db.id})
    refresh_token = create_refresh_token({"sub": user_db.username, "user_id": user_db.id})

    token_db = RefreshToken(token=refresh_token, user_id=user_db.id)
    db.add(token_db)
    db.commit()

    return RedirectResponse(
        f"{FRONTEND_URL}/google-success"
        f"?access_token={access_token}"
        f"&refresh_token={refresh_token}"
    )


@auth_router.post('/register', response_model=dict)
async def register(user_data: UserProfileSchema, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.username == user_data.username).first()
    if user_db:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,detail='Such a username exists.')

    hash_password = get_password_hash(user_data.password)

    user = UserProfile(
        username=user_data.username,
        email=user_data.email,
        age=user_data.age,
        profile_image=user_data.profile_image,
        role=user_data.role,
        password=hash_password
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = create_access_token({
        'sub': user.username,
        'user_id': user.id
    })

    refresh_token = create_refresh_token({
        'sub': user.username,
        'user_id': user.id
    })

    token_db = RefreshToken(
        token=refresh_token,
        user_id=user.id
    )

    db.add(token_db)
    db.commit()

    return {
        'message': 'Successful registration',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user_id': user.id,
        'type': 'bearer'
    }
@auth_router.post('/login', response_model=dict)
async def login(user_data: LoginSchema, db: Session = Depends(get_db)):
    user_db = db.query(UserProfile).filter(UserProfile.username == user_data.username).first()
    if not user_db or not verify_password(user_data.password, user_db.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Incorrect username or password')

    access_token = create_access_token({'sub': user_db.username, 'user_id': user_db.id})
    refresh_token = create_refresh_token({'sub': user_db.username, 'user_id': user_db.id})

    token_db = RefreshToken(token=refresh_token, user_id=user_db.id)
    db.add(token_db)
    db.commit()
    db.refresh(token_db)

    return {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user_id': user_db.id,
        'type': 'bearer'
    }

@auth_router.post('/logout', response_model=dict)
async def logout(data: RefreshTokenSchema, db: Session = Depends(get_db)):
    refresh_db = db.query(RefreshToken).filter(RefreshToken.token == data.refresh_token).first()

    if not refresh_db:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Refresh token not found')

    db.delete(refresh_db)
    db.commit()
    return {'message': 'Success logout'}

@auth_router.post('/access_generate', response_model=dict)
async def generate_access(data: RefreshTokenSchema, db: Session = Depends(get_db)):
    refresh_db = db.query(RefreshToken).filter(RefreshToken.token == data.refresh_token).first()

    if not refresh_db:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid refresh token')

    try:
        payload = decode_token(data.refresh_token)
    except HTTPException:
        db.delete(refresh_db)
        db.commit()
        raise

    username = payload.get('sub')
    user_id = payload.get('user_id')

    if not username or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token payload')

    db.delete(refresh_db)

    new_access_token = create_access_token({'sub': username, 'user_id': user_id})
    new_refresh_token = create_refresh_token({'sub': username, 'user_id': user_id})

    new_token_db = RefreshToken(token=new_refresh_token, user_id=refresh_db.user_id)
    db.add(new_token_db)
    db.commit()

    return {
        'access_token': new_access_token,
        'refresh_token': new_refresh_token,
        'user_id': user_id,
        'type': 'bearer'
    }
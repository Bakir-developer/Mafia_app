import json
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import UserProfile, Game, GamePlayer
from mysite.config import SECRET_KEY, ALGORITHM

chat_router = APIRouter(prefix="/ws", tags=["Chat"])

class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_users: Dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, room_id: int, user_id: int):

        if room_id not in self.active_connections:
            self.active_connections[room_id] = []

        self.active_connections[room_id].append(websocket)

        self.connection_users[websocket] = user_id
    def disconnect(self, websocket: WebSocket, room_id: int):
        if room_id in self.active_connections:

            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)

            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

        self.connection_users.pop(websocket, None)

    async def broadcast(self, room_id: int, data: dict):
        connections = self.active_connections.get(room_id, [])
        disconnected = []

        for websocket in connections:
            try:
                await websocket.send_json(data)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket, room_id)

    async def send_personal(
        self,
        websocket: WebSocket,
        data: dict
    ):
        try:
            await websocket.send_json(data)
        except Exception:
            pass

manager = ConnectionManager()

def decode_websocket_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("JWT PAYLOAD:", payload)
        return payload

    except JWTError as e:
        print("JWT ERROR:", e)
        return None

def get_user_by_token(db: Session, token: str):
    payload = decode_websocket_token(token)

    if not payload:
        print("❌ JWT payload отсутствует")
        return None

    username = payload.get("sub")

    print("JWT USERNAME:", username)

    if not username:
        print("❌ В JWT нет sub")
        return None

    user = db.query(UserProfile).filter(UserProfile.username == username).first()
    print("USER:", user)
    return user

def get_game_player(db: Session, room_id: int, user_id: int):
    game = db.query(Game).filter(Game.room_id == room_id).first()
    print("GAME:", game)

    if not game:
        print("❌ Игра для комнаты не найдена")
        return None

    game_player = db.query(GamePlayer).filter(GamePlayer.game_id == game.id, GamePlayer.user_id == user_id).first()
    print("GAME PLAYER:", game_player)
    return game_player

@chat_router.websocket("/chat/{room_id}")
async def chat_endpoint(websocket: WebSocket, room_id: int, token: str):

    db = SessionLocal()
    user = None

    try:
        await websocket.accept()

        print("\n==============================")
        print("WEBSOCKET CONNECTED")
        print("ROOM:", room_id)
        print("==============================")

        user = get_user_by_token(db, token)

        if not user:
            print("❌ USER NOT FOUND")

            await websocket.send_json({
                "type": "error",
                "detail": "Invalid token or user not found"
            })

            await websocket.close(code=1008)
            return

        print(f"✅ USER FOUND: " f"id={user.id}, username={user.username}")

        game_player = get_game_player(db, room_id, user.id)

        if not game_player:
            print("❌ GAME PLAYER NOT FOUND")

            await websocket.send_json({
                "type": "error",
                "detail": "You are not a player in this game"
            })

            await websocket.close(code=1008)
            return

        print(f"✅ GAME PLAYER FOUND: " f"id={game_player.id}")

        await manager.connect(websocket, room_id, user.id)

        await manager.broadcast(
            room_id,
            {
                "type": "user_joined",
                "user_id": user.id,
                "username": user.username
            }
        )

        while True:
            raw = await websocket.receive_text()

            print("RAW MESSAGE:", raw)

            try:

                data = json.loads(raw)

                message = data.get(
                    "message",
                    ""
                )

            except json.JSONDecodeError:

                message = raw

            if not isinstance(message, str):

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message must be text"
                    }
                )

                continue

            message = message.strip()

            if not message:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message is empty"
                    }
                )

                continue

            game_player = get_game_player(db, room_id, user.id)

            if not game_player:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Player not found"
                    }
                )

                continue

            if game_player.is_alive:

                await manager.broadcast(
                    room_id,
                    {
                        "type": "message",
                        "user_id": user.id,
                        "username": user.username,
                        "message": message
                    }
                )

                continue

            if game_player.has_sent_last_words:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Ты уже сказал последние слова"
                    }
                )

                continue

            game_player.has_sent_last_words = True
            db.commit()

            await manager.broadcast(
                room_id,
                {
                    "type": "last_words",
                    "user_id": user.id,
                    "username": user.username,
                    "message": message
                }
            )

    except WebSocketDisconnect:

        print("❌ WEBSOCKET DISCONNECTED")

        manager.disconnect(websocket,room_id)

        if user:
            await manager.broadcast(
                room_id,
                {
                    "type": "user_left",
                    "user_id": user.id,
                    "username": user.username
                }
            )

    except Exception as e:
        print("WEBSOCKET ERROR:", repr(e))
        manager.disconnect(websocket, room_id)
    finally:
        db.close()
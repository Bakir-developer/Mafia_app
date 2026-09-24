import json
from datetime import datetime
from typing import Dict, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from mysite.db.database import SessionLocal
from mysite.db.models import (UserProfile, Game, GamePlayer, GamePhase, GameRole,)
from mysite.config import SECRET_KEY, ALGORITHM

chat_router = APIRouter(prefix="/ws", tags=["Chat"])

class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_users: Dict[WebSocket, int] = {}

        self.connection_games: Dict[WebSocket, int] = {}

    async def connect(
        self,
        websocket: WebSocket,
        game_id: int,
        user_id: int
    ):
        if game_id not in self.active_connections:
            self.active_connections[game_id] = []

        self.active_connections[game_id].append(websocket)

        self.connection_users[websocket] = user_id
        self.connection_games[websocket] = game_id

    def disconnect(
        self,
        websocket: WebSocket,
        game_id: int
    ):
        if game_id in self.active_connections:

            if websocket in self.active_connections[game_id]:
                self.active_connections[game_id].remove(websocket)

            if not self.active_connections[game_id]:
                del self.active_connections[game_id]

        self.connection_users.pop(websocket, None)
        self.connection_games.pop(websocket, None)

    async def broadcast(
        self,
        game_id: int,
        data: dict
    ):
        connections = self.active_connections.get(game_id, [])

        disconnected = []

        for websocket in connections:

            try:
                await websocket.send_json(data)

            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket, game_id)

    async def send_personal(
        self,
        websocket: WebSocket,
        data: dict
    ):
        try:
            await websocket.send_json(data)

        except Exception:
            pass

    async def broadcast_channel(
        self,
        game_id: int,
        channel: str,
        data: dict,
        db: Session
    ):

        connections = self.active_connections.get(game_id, [])

        disconnected = []

        for websocket in connections:

            user_id = self.connection_users.get(websocket)

            if not user_id:
                continue

            game_player = (
                db.query(GamePlayer)
                .filter(
                    GamePlayer.game_id == game_id,
                    GamePlayer.user_id == user_id
                )
                .first()
            )

            if not game_player:
                continue

            if channel == "dead":

                if game_player.is_alive:
                    continue

            elif channel == "mafia":

                if not game_player.is_alive:
                    continue

                if game_player.role != GameRole.mafia:
                    continue

            elif channel == "all":

                if not game_player.is_alive:
                    continue

            try:
                await websocket.send_json(data)

            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket, game_id)


manager = ConnectionManager()


def decode_websocket_token(token: str):

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        print("JWT PAYLOAD:", payload)

        return payload

    except JWTError as e:

        print("JWT ERROR:", e)

        return None


def get_user_by_token(
    db: Session,
    token: str
):

    payload = decode_websocket_token(token)

    if not payload:
        return None

    username = payload.get("sub")

    if not username:
        print("❌ В JWT нет sub")
        return None

    user = (
        db.query(UserProfile)
        .filter(UserProfile.username == username)
        .first()
    )

    print("USER:", user)

    return user


def get_game_player(
    db: Session,
    game_id: int,
    user_id: int
):

    game_player = (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id
        )
        .first()
    )

    print("GAME PLAYER:", game_player)

    return game_player


def get_game(
    db: Session,
    game_id: int
):

    game = (
        db.query(Game)
        .filter(Game.id == game_id)
        .first()
    )

    print("GAME:", game)

    return game


def can_send_message(
    game: Game,
    game_player: GamePlayer,
    channel: str
):

    if game.winner is not None:

        if channel == "all":
            return True

        if channel == "dead" and not game_player.is_alive:
            return True

        return False

    if channel == "dead":

        if not game_player.is_alive:
            return True

        return False

    # MAfia CHAT
    if channel == "mafia":

        if game.current_phase != GamePhase.NIGHT:
            return False

        if not game_player.is_alive:
            return False

        if game_player.role != GameRole.mafia:
            return False

        return True

    # ALL CHAT
    if channel == "all":

        if game.current_phase != GamePhase.DAY:
            return False

        if not game_player.is_alive:
            return False

        return True

    return False


@chat_router.websocket("/game/{game_id}")
async def chat_endpoint(
    websocket: WebSocket,
    game_id: int,
    token: str
):

    db = SessionLocal()

    user = None
    game_player = None

    try:

        await websocket.accept()

        print("\n==============================")
        print("WEBSOCKET CONNECTED")
        print("GAME:", game_id)
        print("==============================")

        user = get_user_by_token(
            db,
            token
        )

        if not user:

            await websocket.send_json({
                "type": "error",
                "detail": "Invalid token or user not found"
            })

            await websocket.close(code=1008)

            return

        print(
            f"✅ USER FOUND: "
            f"id={user.id}, username={user.username}"
        )

        game = get_game(
            db,
            game_id
        )

        if not game:

            await websocket.send_json({
                "type": "error",
                "detail": "Game not found"
            })

            await websocket.close(code=1008)

            return

        game_player = get_game_player(
            db,
            game_id,
            user.id
        )

        if not game_player:

            await websocket.send_json({
                "type": "error",
                "detail": "You are not a player in this game"
            })

            await websocket.close(code=1008)

            return

        print(
            f"✅ GAME PLAYER FOUND: "
            f"id={game_player.id}, "
            f"role={game_player.role}, "
            f"alive={game_player.is_alive}"
        )

        await manager.connect(
            websocket,
            game_id,
            user.id
        )

        await manager.broadcast(
            game_id,
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

            except json.JSONDecodeError:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message must be valid JSON"
                    }
                )

                continue

            if not isinstance(data, dict):

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Invalid message format"
                    }
                )

                continue

            message_type = data.get("type")

            if message_type != "chat":

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Only chat messages are supported"
                    }
                )

                continue

            channel = data.get("channel")

            allowed_channels = {
                "all",
                "mafia",
                "dead"
            }

            if channel not in allowed_channels:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Invalid channel"
                    }
                )

                continue

            text = data.get("text", "")

            if not isinstance(text, str):

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Text must be string"
                    }
                )

                continue

            text = text.strip()

            if not text:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message is empty"
                    }
                )

                continue

            db.expire_all()

            game = get_game(
                db,
                game_id
            )

            game_player = get_game_player(
                db,
                game_id,
                user.id
            )

            if not game or not game_player:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Game or player not found"
                    }
                )

                continue

            if not can_send_message(
                game,
                game_player,
                channel
            ):

                if channel == "all":

                    detail = (
                        "Общий чат доступен "
                        "только живым игрокам днём"
                    )

                elif channel == "mafia":

                    detail = (
                        "Чат мафии доступен "
                        "только живым мафиози ночью"
                    )

                else:

                    detail = (
                        "Чат мёртвых доступен "
                        "только мёртвым игрокам"
                    )

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": detail
                    }
                )

                continue

            message_time = datetime.utcnow().isoformat()

            await manager.broadcast_channel(
                game_id,
                channel,
                {
                    "type": "chat",
                    "channel": channel,
                    "from": user.username,
                    "user_id": user.id,
                    "text": text,
                    "time": message_time
                },
                db
            )

    except WebSocketDisconnect:

        print("❌ WEBSOCKET DISCONNECTED")

        manager.disconnect(websocket, game_id)

        if user:
            await manager.broadcast(
                game_id,
                {
                    "type": "user_left",
                    "user_id": user.id,
                    "username": user.username
                }
            )

    except Exception as e:
        print("WEBSOCKET ERROR:", repr(e))

        manager.disconnect(websocket, game_id)

    finally:
        db.close()
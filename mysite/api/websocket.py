import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from mysite.db.database import SessionLocal
from mysite.db.models import UserProfile, Game, GamePlayer, GamePhase, GameRole
from mysite.config import SECRET_KEY, ALGORITHM

logger = logging.getLogger(__name__)

chat_router = APIRouter(prefix="/ws", tags=["Chat"])

MAX_MESSAGE_LENGTH = 500

ALLOWED_CHANNELS = {"all", "mafia", "dead"}

CHANNEL_ERRORS = {
    "all": "Общий чат доступен только живым игрокам днём",
    "mafia": "Чат мафии доступен только живым мафиози ночью",
    "dead": "Чат мёртвых доступен только мёртвым игрокам",
}

# user_id -> (жив ли игрок, его роль). Собирается один раз на сообщение,
# чтобы не держать соединение с БД открытым во время отправки по сокетам.
PlayersState = Dict[int, Tuple[bool, GameRole]]


class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_users: Dict[WebSocket, int] = {}
        self.connection_games: Dict[WebSocket, int] = {}

    async def connect(
        self,
        websocket: WebSocket,
        game_id: int,
        user_id: int,
    ):
        self.active_connections.setdefault(game_id, []).append(websocket)

        self.connection_users[websocket] = user_id
        self.connection_games[websocket] = game_id

        logger.debug(
            "ws connect: game=%s user=%s total=%s",
            game_id,
            user_id,
            len(self.active_connections[game_id]),
        )

    def disconnect(
        self,
        websocket: WebSocket,
        game_id: int,
    ):
        connections = self.active_connections.get(game_id)

        if connections is not None:

            if websocket in connections:
                connections.remove(websocket)

            if not connections:
                del self.active_connections[game_id]

        self.connection_users.pop(websocket, None)
        self.connection_games.pop(websocket, None)

    async def broadcast(
        self,
        game_id: int,
        data: dict,
    ):
        # Enum и datetime (phase, phase_ends_at) не сериализуются send_json напрямую,
        # поэтому сначала приводим всё к JSON-совместимому виду.
        data = jsonable_encoder(data)

        disconnected = []

        # list(...) — копия: пока мы ждём await, список могут изменить другие корутины
        for websocket in list(self.active_connections.get(game_id, [])):

            try:
                await websocket.send_json(data)

            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket, game_id)

    async def send_personal(
        self,
        websocket: WebSocket,
        data: dict,
    ):
        data = jsonable_encoder(data)

        try:
            await websocket.send_json(data)

        except Exception:
            pass

    async def broadcast_channel(
        self,
        game_id: int,
        channel: str,
        data: dict,
        players_state: PlayersState,
        game_finished: bool = False,
    ):
        data = jsonable_encoder(data)

        disconnected = []

        for websocket in list(self.active_connections.get(game_id, [])):

            user_id = self.connection_users.get(websocket)

            if user_id is None:
                continue

            state = players_state.get(user_id)

            if state is None:
                continue

            is_alive, role = state

            if channel == "dead":
                if is_alive:
                    continue

            elif channel == "mafia":
                if not is_alive:
                    continue

                if role != GameRole.mafia:
                    continue

            elif channel == "all":
                # после конца игры общий чат видят все, включая мёртвых
                if not is_alive and not game_finished:
                    continue

            else:
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

        return jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

    except JWTError as e:

        logger.warning("JWT error: %s", e)

        return None


def get_user_by_token(
    db: Session,
    token: str,
):

    payload = decode_websocket_token(token)

    if not payload:
        return None

    username = payload.get("sub")

    if not username:
        logger.warning("JWT has no 'sub'")
        return None

    return (
        db.query(UserProfile)
        .filter(UserProfile.username == username)
        .first()
    )


def get_game_player(
    db: Session,
    game_id: int,
    user_id: int,
):

    return (
        db.query(GamePlayer)
        .filter(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
        .first()
    )


def get_game(
    db: Session,
    game_id: int,
):

    return (
        db.query(Game)
        .filter(Game.id == game_id)
        .first()
    )


def can_send_message(
    game: Game,
    game_player: GamePlayer,
    channel: str,
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

    # Чат мафии
    if channel == "mafia":

        if game.current_phase != GamePhase.NIGHT:
            return False

        if not game_player.is_alive:
            return False

        if game_player.role != GameRole.mafia:
            return False

        return True

    # Общий чат
    if channel == "all":

        if game.current_phase != GamePhase.DAY:
            return False

        if not game_player.is_alive:
            return False

        return True

    return False


async def reject_connection(
    websocket: WebSocket,
    detail: str,
):

    await manager.send_personal(
        websocket,
        {
            "type": "error",
            "detail": detail,
        },
    )

    try:
        await websocket.close(code=1008)

    except Exception:
        pass


@chat_router.websocket("/game/{game_id}")
async def chat_endpoint(
    websocket: WebSocket,
    game_id: int,
    token: str,
):

    user_id: Optional[int] = None
    username: Optional[str] = None
    connected = False

    try:

        await websocket.accept()

        # --- Авторизация: короткая сессия, закрывается до входа в цикл ---
        game_exists = False
        is_player = False

        with SessionLocal() as db:

            user = get_user_by_token(db, token)

            if user is not None:

                user_id = user.id
                username = user.username

                game_exists = get_game(db, game_id) is not None

                if game_exists:
                    is_player = get_game_player(db, game_id, user.id) is not None

        if user_id is None:
            await reject_connection(websocket, "Invalid token or user not found")
            return

        if not game_exists:
            await reject_connection(websocket, "Game not found")
            return

        if not is_player:
            await reject_connection(websocket, "You are not a player in this game")
            return

        await manager.connect(
            websocket,
            game_id,
            user_id,
        )

        connected = True

        await manager.broadcast(
            game_id,
            {
                "type": "user_joined",
                "user_id": user_id,
                "username": username,
            },
        )

        while True:

            raw = await websocket.receive_text()

            try:

                data = json.loads(raw)

            except json.JSONDecodeError:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message must be valid JSON",
                    },
                )

                continue

            if not isinstance(data, dict):

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Invalid message format",
                    },
                )

                continue

            if data.get("type") != "chat":

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Only chat messages are supported",
                    },
                )

                continue

            channel = data.get("channel")

            if channel not in ALLOWED_CHANNELS:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Invalid channel",
                    },
                )

                continue

            text = data.get("text", "")

            if not isinstance(text, str):

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Text must be string",
                    },
                )

                continue

            text = text.strip()

            if not text:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": "Message is empty",
                    },
                )

                continue

            if len(text) > MAX_MESSAGE_LENGTH:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": f"Message is too long (max {MAX_MESSAGE_LENGTH} characters)",
                    },
                )

                continue

            # --- Новая короткая сессия на каждое сообщение: всегда свежее состояние
            # игры, и соединение с БД не занято, пока мы ждём сеть ---
            error_detail = None
            players_state: PlayersState = {}
            game_finished = False

            with SessionLocal() as db:

                game = get_game(db, game_id)
                game_player = get_game_player(db, game_id, user_id)

                if not game or not game_player:

                    error_detail = "Game or player not found"

                elif not can_send_message(game, game_player, channel):

                    error_detail = CHANNEL_ERRORS[channel]

                else:

                    game_finished = game.winner is not None

                    players_state = {
                        player.user_id: (player.is_alive, player.role)
                        for player in (
                            db.query(GamePlayer)
                            .filter(GamePlayer.game_id == game_id)
                            .all()
                        )
                    }

            if error_detail is not None:

                await manager.send_personal(
                    websocket,
                    {
                        "type": "error",
                        "detail": error_detail,
                    },
                )

                continue

            await manager.broadcast_channel(
                game_id,
                channel,
                {
                    "type": "chat",
                    "channel": channel,
                    "from": username,
                    "user_id": user_id,
                    "text": text,
                    "time": datetime.utcnow().isoformat(),
                },
                players_state,
                game_finished,
            )

    except WebSocketDisconnect:

        logger.info("ws disconnected: game=%s user=%s", game_id, user_id)

    except Exception:

        logger.exception("ws error: game=%s user=%s", game_id, user_id)

    finally:

        if connected:

            manager.disconnect(websocket, game_id)

            await manager.broadcast(
                game_id,
                {
                    "type": "user_left",
                    "user_id": user_id,
                    "username": username,
                },
            )
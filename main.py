from fastapi import FastAPI
from mysite.api import (user_profile, auth, statistic, room, room_player, reviews,
                        game, night_action, timing, websocket)
from mysite.admin.setup import setup_admin
from fastapi.middleware.cors import CORSMiddleware

Mafia_app = FastAPI(title='FastAPI Mafia_app')
Mafia_app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


Mafia_app.include_router(room.room_router)
Mafia_app.include_router(room_player.room_player_router)
Mafia_app.include_router(user_profile.user_router)
Mafia_app.include_router(auth.auth_router)
Mafia_app.include_router(statistic.statistic_router)
Mafia_app.include_router(reviews.review_router)
Mafia_app.include_router(game.game_router)
Mafia_app.include_router(game.game_player_router)
Mafia_app.include_router(game.game_round_router)
Mafia_app.include_router(night_action.night_action_router)
Mafia_app.include_router(night_action.vote_router)
Mafia_app.include_router(night_action.achievement_router)
Mafia_app.include_router(night_action.user_achievement_router)
Mafia_app.include_router(websocket.chat_router)
Mafia_app.include_router(timing.chat_router)

setup_admin(Mafia_app)

"""
database.py – All MongoDB operations via async Motor driver.

Collections:
  users        – stats, ELO, coins, streak, language per user
  groups       – registered groups/supergroups
  group_stats  – per-group win/loss/draw per user
  tournaments  – active bracket tournaments
"""

import math
from datetime import datetime, date

from motor.motor_asyncio import AsyncIOMotorClient

from config import MONGO_URI, DB_NAME

# ── Connection ────────────────────────────────────────────
client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db     = client[DB_NAME]

users_col       = db["users"]
groups_col      = db["groups"]
group_stats_col = db["group_stats"]
tournaments_col = db["tournaments"]

# ── Constants ─────────────────────────────────────────────
STARTING_ELO   = 1500
STARTING_COINS = 100
COINS_WIN      = 50
COINS_DRAW     = 20
COINS_DAILY    = 30
ELO_K          = 32


# ── Indexes (run once on startup) ─────────────────────────

async def ensure_indexes():
    await users_col.create_index("user_id", unique=True)
    await groups_col.create_index("chat_id", unique=True)
    await group_stats_col.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
    await group_stats_col.create_index([("chat_id", 1), ("wins", -1)])
    await tournaments_col.create_index("chat_id")


# ── ELO math ──────────────────────────────────────────────

def _expected(ra: int, rb: int) -> float:
    return 1.0 / (1.0 + math.pow(10, (rb - ra) / 400.0))


def calc_new_elo(rating: int, opp_rating: int, score: float) -> int:
    """score: 1.0 = win, 0.5 = draw, 0.0 = loss"""
    return int(rating + ELO_K * (score - _expected(rating, opp_rating)))


# ─────────────────────────────────────────────────────────
#  USER OPERATIONS
# ─────────────────────────────────────────────────────────

async def save_user(user) -> None:
    """Upsert Telegram user; initialises stats on first insert."""
    await users_col.update_one(
        {"user_id": user.id},
        {
            "$set": {
                "username":  user.username,
                "full_name": user.full_name,
                "last_seen": datetime.utcnow(),
            },
            "$setOnInsert": {
                "user_id":    user.id,
                "joined":     datetime.utcnow(),
                "wins":       0,
                "losses":     0,
                "draws":      0,
                "elo":        STARTING_ELO,
                "coins":      STARTING_COINS,
                "streak":     0,
                "max_streak": 0,
                "daily_date": None,
                "lang":       "en",
            },
        },
        upsert=True,
    )


async def get_user(user_id: int) -> dict | None:
    return await users_col.find_one({"user_id": user_id})


async def get_user_lang(user_id: int) -> str:
    doc = await users_col.find_one({"user_id": user_id}, {"lang": 1})
    return (doc or {}).get("lang", "en")


async def set_user_lang(user_id: int, lang: str) -> None:
    await users_col.update_one({"user_id": user_id}, {"$set": {"lang": lang}})


async def count_users() -> int:
    return await users_col.count_documents({})


async def get_all_user_ids() -> list:
    return [d["user_id"] async for d in users_col.find({}, {"user_id": 1})]


async def get_user_coins(user_id: int) -> int:
    doc = await users_col.find_one({"user_id": user_id}, {"coins": 1})
    return (doc or {}).get("coins", 0)


async def add_coins(user_id: int, amount: int) -> None:
    await users_col.update_one({"user_id": user_id}, {"$inc": {"coins": amount}})


async def deduct_coins(user_id: int, amount: int) -> bool:
    """Returns True on success, False if balance is insufficient."""
    doc = await users_col.find_one({"user_id": user_id}, {"coins": 1})
    if (doc or {}).get("coins", 0) < amount:
        return False
    await users_col.update_one({"user_id": user_id}, {"$inc": {"coins": -amount}})
    return True


async def update_user_stats_full(user_id: int, result: str, opponent_elo: int) -> dict:
    """
    Atomically updates wins/losses/draws, ELO, coins, streak.
    Returns a delta dict for display (old_elo, new_elo, elo_delta, coins_add, streak, prev_streak).
    """
    doc = await users_col.find_one({"user_id": user_id})
    if not doc:
        return {}

    old_elo    = doc.get("elo",        STARTING_ELO)
    old_streak = doc.get("streak",     0)
    old_max    = doc.get("max_streak", 0)

    score_map  = {"win": 1.0, "draw": 0.5, "loss": 0.0}
    new_elo_v  = calc_new_elo(old_elo, opponent_elo, score_map.get(result, 0.0))
    elo_delta  = new_elo_v - old_elo
    coins_add  = COINS_WIN if result == "win" else (COINS_DRAW if result == "draw" else 0)
    new_streak = (old_streak + 1) if result == "win" else 0
    new_max    = max(old_max, new_streak)

    stat_field = {"win": "wins", "loss": "losses", "draw": "draws"}.get(result, "draws")

    await users_col.update_one(
        {"user_id": user_id},
        {
            "$inc": {stat_field: 1, "elo": elo_delta, "coins": coins_add},
            "$set": {"streak": new_streak, "max_streak": new_max},
        },
    )
    return {
        "old_elo":     old_elo,
        "new_elo":     new_elo_v,
        "elo_delta":   elo_delta,
        "coins_add":   coins_add,
        "streak":      new_streak,
        "prev_streak": old_streak,
    }


async def get_leaderboard(limit: int = 10) -> list:
    cursor = users_col.find(
        {"wins": {"$gt": 0}},
        {"user_id": 1, "full_name": 1, "username": 1, "wins": 1,
         "losses": 1, "draws": 1, "elo": 1, "streak": 1},
    ).sort("elo", -1).limit(limit)
    return [doc async for doc in cursor]


# ─────────────────────────────────────────────────────────
#  GROUP OPERATIONS
# ─────────────────────────────────────────────────────────

async def save_group(chat) -> None:
    """Upsert a Telegram group/supergroup."""
    await groups_col.update_one(
        {"chat_id": chat.id},
        {
            "$set": {
                "title":     chat.title,
                "username":  getattr(chat, "username", None),
                "last_seen": datetime.utcnow(),
            },
            "$setOnInsert": {
                "chat_id": chat.id,
                "joined":  datetime.utcnow(),
            },
        },
        upsert=True,
    )


async def count_groups() -> int:
    return await groups_col.count_documents({})


async def get_all_group_ids() -> list:
    return [d["chat_id"] async for d in groups_col.find({}, {"chat_id": 1})]


# ─────────────────────────────────────────────────────────
#  GROUP STATS (per-group leaderboard)
# ─────────────────────────────────────────────────────────

async def update_group_stats(chat_id: int, user_id: int, result: str, user_name: str = "") -> int:
    """Increments the player's group-level stats. Returns new group win count."""
    stat_field = {"win": "wins", "loss": "losses", "draw": "draws"}.get(result)
    if not stat_field:
        return 0

    await group_stats_col.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {
            "$inc": {stat_field: 1},
            "$setOnInsert": {
                "chat_id":   chat_id,
                "user_id":   user_id,
                "user_name": user_name,
                "wins":      0,
                "losses":    0,
                "draws":     0,
            },
        },
        upsert=True,
    )
    doc = await group_stats_col.find_one(
        {"chat_id": chat_id, "user_id": user_id}, {"wins": 1}
    )
    return (doc or {}).get("wins", 0)


async def get_group_leaderboard(chat_id: int, limit: int = 10) -> list:
    cursor = group_stats_col.find(
        {"chat_id": chat_id, "wins": {"$gt": 0}},
        {"user_id": 1, "user_name": 1, "wins": 1, "losses": 1, "draws": 1},
    ).sort("wins", -1).limit(limit)
    return [doc async for doc in cursor]


# ─────────────────────────────────────────────────────────
#  DAILY CHALLENGE
# ─────────────────────────────────────────────────────────

async def check_daily_available(user_id: int) -> bool:
    """True if the user has NOT completed today's challenge yet."""
    today = date.today().isoformat()
    doc   = await users_col.find_one({"user_id": user_id}, {"daily_date": 1})
    return (doc or {}).get("daily_date") != today


async def mark_daily_done(user_id: int) -> None:
    today = date.today().isoformat()
    await users_col.update_one({"user_id": user_id}, {"$set": {"daily_date": today}})
    await add_coins(user_id, COINS_DAILY)


# ─────────────────────────────────────────────────────────
#  TOURNAMENT
# ─────────────────────────────────────────────────────────

async def create_tournament(chat_id: int, creator_id: int, size: int) -> dict:
    doc = {
        "chat_id":    chat_id,
        "creator_id": creator_id,
        "size":       size,
        "status":     "waiting",   # waiting | active | finished
        "players":    [],
        "bracket":    [],
        "round":      0,
        "created":    datetime.utcnow(),
    }
    await tournaments_col.delete_many({"chat_id": chat_id})
    await tournaments_col.insert_one(doc)
    return doc


async def get_tournament(chat_id: int) -> dict | None:
    return await tournaments_col.find_one({"chat_id": chat_id})


async def update_tournament(chat_id: int, upd: dict) -> None:
    await tournaments_col.update_one({"chat_id": chat_id}, {"$set": upd})


async def delete_tournament(chat_id: int) -> None:
    await tournaments_col.delete_many({"chat_id": chat_id})


# ─────────────────────────────────────────────────────────
#  BROADCAST
# ─────────────────────────────────────────────────────────

async def get_all_recipients() -> list:
    """
    Returns all user IDs + group IDs combined.
    FIX: await each list separately before concatenating.
    """
    user_ids  = await get_all_user_ids()
    group_ids = await get_all_group_ids()
    return user_ids + group_ids

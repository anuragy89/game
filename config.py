"""
config.py – All environment variables and bot constants
Copy .env.example → .env and fill in your values before running.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Core ──────────────────────────────────────────────────
BOT_TOKEN        = os.getenv("BOT_TOKEN",        "YOUR_BOT_TOKEN_HERE")
BOT_USERNAME     = os.getenv("BOT_USERNAME",     "YourBotUsername")   # without @

# ── MongoDB ───────────────────────────────────────────────
MONGO_URI        = os.getenv("MONGO_URI",        "mongodb+srv://user:pass@cluster.mongodb.net/xobot")
DB_NAME          = os.getenv("DB_NAME",          "xobot")

# ── Links ─────────────────────────────────────────────────
UPDATE_CHANNEL   = os.getenv("UPDATE_CHANNEL",   "@YourChannel")      # with @
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "YourSupport")       # without @
OWNER_ID         = int(os.getenv("OWNER_ID",     "123456789"))

# ── Gameplay ──────────────────────────────────────────────
BOT_THINK_DELAY  = float(os.getenv("BOT_THINK_DELAY", "1.2"))        # bot "thinking" pause (sec)

# ── Heroku webhook ────────────────────────────────────────
PORT             = int(os.getenv("PORT",         "8443"))
WEBHOOK_URL      = os.getenv("WEBHOOK_URL",      "")                  # e.g. https://myapp.herokuapp.com
USE_WEBHOOK      = bool(WEBHOOK_URL)

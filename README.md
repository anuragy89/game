# 🎮 XO Telegram Bot

> **Production-ready Tic-Tac-Toe bot for Telegram groups.**
> PvP · AI opponent · Tournaments · ELO · Coins · Multilingual

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/anuragy89/game)

---

## ✨ Features

| Category | Features |
|---|---|
| 🎮 **Gameplay** | PvP (challenge any user), PvE (Easy/Medium/Hard AI), Inline board |
| 🧠 **AI** | Unbeatable Minimax + alpha-beta pruning, bot personality & taunts |
| 🏆 **Tournaments** | Single-elimination brackets (4 or 8 players), auto-advances rounds |
| 💰 **Economy** | Coins per win/draw, pre-game betting, daily puzzle rewards |
| 📅 **Daily Challenge** | New puzzle every day, earn free coins for solving it |
| 📊 **Stats** | ELO rating, win streaks, global leaderboard, per-group leaderboard |
| 🎉 **Milestones** | Auto-announcements at 10 / 25 / 50 / 100 group wins |
| 🌐 **Languages** | English 🇬🇧, Arabic 🇸🇦, Hindi 🇮🇳 |
| 📡 **Broadcast** | Owner-only: send messages to all users + groups |
| 🚀 **Scale** | MongoDB async (Motor), safe for 10,000+ groups |

---

## 🗂️ File Structure

```
xo-telegram-bot/
│
├── bot.py                        ← Entry point (webhook / polling)
├── config.py                     ← All env var loading
├── game.py                       ← Core game logic + Minimax AI
├── keyboards.py                  ← All InlineKeyboardMarkup builders
├── database.py                   ← MongoDB (async Motor) — all DB ops
├── i18n.py                       ← Translations: EN / AR / HI
│
├── handlers/
│   ├── __init__.py
│   ├── game_handler.py           ← PvP, PvE, moves, end-game, ELO
│   ├── user_handler.py           ← /start, /help, /stats, /top, menus
│   ├── admin_handler.py          ← /broadcast, /adminstats (owner only)
│   ├── coins_handler.py          ← /coins, /bet, bet resolution
│   ├── daily_handler.py          ← /daily puzzle challenge
│   └── tournament_handler.py     ← /tournament bracket system
│
├── app.json                      ← Heroku one-click deploy config
├── Procfile                      ← Heroku process definition
├── runtime.txt                   ← Python version pin
├── requirements.txt              ← Python dependencies
│
├── .env.example                  ← Template for your .env file
├── .gitignore                    ← Ignores .env, __pycache__, etc.
└── README.md                     ← This file
```

---

## 🚀 Quick Deploy (Heroku — Recommended)

### Option 1: One-Click Deploy Button
Click the **Deploy to Heroku** button at the top of this README.
Fill in the environment variables in the Heroku UI and click Deploy.

**After deploy, set WEBHOOK_URL:**
```bash
heroku config:set WEBHOOK_URL=https://YOUR-APP-NAME.herokuapp.com -a YOUR-APP-NAME
```

### Option 2: Manual Heroku Deploy

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/xo-telegram-bot.git
cd xo-telegram-bot

# 2. Create Heroku app
heroku login
heroku create your-xo-bot-name

# 3. Set all config vars
heroku config:set \
  BOT_TOKEN="your_bot_token" \
  BOT_USERNAME="YourBotUsername" \
  MONGO_URI="mongodb+srv://user:pass@cluster.mongodb.net/xobot" \
  DB_NAME="xobot" \
  UPDATE_CHANNEL="@YourChannel" \
  SUPPORT_USERNAME="YourSupport" \
  OWNER_ID="123456789" \
  WEBHOOK_URL="https://your-xo-bot-name.herokuapp.com"

# 4. Deploy
git push heroku main

# 5. Scale to Standard 2x (no sleep, always on)
heroku ps:type web=standard-2x
heroku ps:scale web=1

# 6. Check logs
heroku logs --tail
```

### Option 3: Auto-Deploy from GitHub
1. Go to **Heroku Dashboard** → your app → **Deploy** tab
2. Connect to **GitHub** → select your repo
3. Enable **Automatic Deploys** from `main` branch ✅
4. Every `git push` to `main` deploys automatically

---

## 🖥️ Local Development

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/xo-telegram-bot.git
cd xo-telegram-bot

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment
cp .env.example .env
# Edit .env with your values (leave WEBHOOK_URL blank for polling mode)

# 5. Run
python bot.py
```

---

## ⚙️ Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | From [@BotFather](https://t.me/BotFather) |
| `BOT_USERNAME` | ✅ | Bot username without `@` |
| `MONGO_URI` | ✅ | MongoDB Atlas connection string |
| `DB_NAME` | ✅ | Database name (e.g. `xobot`) |
| `UPDATE_CHANNEL` | ✅ | Your update channel with `@` |
| `SUPPORT_USERNAME` | ✅ | Support contact without `@` |
| `OWNER_ID` | ✅ | Your Telegram user ID (from [@userinfobot](https://t.me/userinfobot)) |
| `WEBHOOK_URL` | ⚠️ | Set after deploy: `https://your-app.herokuapp.com` |
| `BOT_THINK_DELAY` | ❌ | AI "think" pause in seconds (default: `1.2`) |
| `PORT` | ❌ | Auto-set by Heroku |

---

## 📋 Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome screen & main menu |
| `/pvp @user` | Challenge a player |
| `/pve` | Play vs AI bot (pick difficulty) |
| `/accept` | Accept a challenge |
| `/decline` | Decline a challenge |
| `/board` | Redisplay current board |
| `/quit` | Abandon current game |
| `/tournament` | Start or join a bracket |
| `/daily` | Today's puzzle (+coins reward) |
| `/coins` | Your coin balance |
| `/bet <amount>` | Bet coins before a game |
| `/stats` | Your stats & ELO rating |
| `/top` | Global ELO leaderboard |
| `/grouptop` | This group's leaderboard |
| `/language` | Change language (EN/AR/HI) |
| `/help` | All commands & guide |
| `/broadcast` | 🔒 Owner: send message to all |
| `/adminstats` | 🔒 Owner: user & group counts |

---

## 🎨 Button Colour System

Telegram doesn't support native button background colours, so a consistent emoji palette is used:

| Emoji | Colour | Used For |
|---|---|---|
| 🟢 | Green | Accept, Join, Easy difficulty |
| 🔴 | Red | Decline, Hard, Cancel, Quit |
| 🟡 | Yellow | Medium difficulty, Caution |
| 🔵 | Blue | Stats, Help, Navigation, Info |
| 🟣 | Purple | Tournament, Leaderboard, Premium |
| 🟠 | Orange | Rematch, Start, Action buttons |

---

## 🛡️ Architecture Notes

- **In-memory game state** (`dict`) — handles 10k+ concurrent groups on one Standard 2x dyno
- **MongoDB Motor** — fully async, non-blocking, never stalls the event loop
- **Broadcast rate** — 20 msg/sec (`asyncio.sleep(0.05)`) — safe within Telegram limits
- **Webhook on Heroku** — Standard 2x never sleeps; polling used locally
- **ELO** — K=32, starting rating 1500, updates per game
- **Minimax + alpha-beta** — unbeatable on Hard; randomised on Easy/Medium

---

## 📦 Dependencies

```
python-telegram-bot==21.5   # Telegram Bot API wrapper
motor==3.5.1                 # Async MongoDB driver
pymongo==4.8.0               # MongoDB client
python-dotenv==1.0.1         # .env file support
```

---

## 📄 License

MIT — free to use, modify and distribute.

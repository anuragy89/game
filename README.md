# 🎭 Truth & Dare Telegram Bot

A **fun, addictive, and scalable Truth & Dare Telegram bot** designed for group chats.  
Built with **Node.js, Telegraf, MongoDB**, and fully **Heroku-ready** 🚀

---

## ✨ Features

- 🎮 Truth & Dare gameplay for Telegram groups
- ⭐ XP & **auto-calculated Level system** (no level desync bugs)
- 🏆 Global leaderboard
- 🎁 Daily rewards system
- 📊 Group analytics (games, truth, dare stats)
- 🚫 Anti-spam & moderation (flood + banned words)
- 📢 Owner-only broadcast system
- 🌍 Multi-language ready (English / Hindi)
- 🧠 Clean & scalable architecture
- 🚀 One-click Heroku deployment

---

## 🧠 XP → Level System

Levels are **NOT stored in the database**.  
They are **calculated dynamically from XP**, making the system bug-proof.

### 📈 Level Formula


XP needed increases with level:
Level 1 → 2 : 100 XP
Level 2 → 3 : 300 XP
Level 3 → 4 : 600 XP
Level 4 → 5 : 1000 XP


✔ Infinite scaling  
✔ RPG-style progression  
✔ No data corruption  

---

## 🤖 Bot Commands

### 👤 User Commands


/start – Start the bot
/help – Show help menu
/truth – Get a truth question (group only)
/dare – Get a dare challenge (group only)
/profile – View your XP & level
/leaderboard – Top players globally
/daily – Claim daily XP reward


### 👥 Group Commands

/analytics – View group game statistics


### 👑 Owner Only

/broadcast<massage>-send massage to all user and groups .


---

## 🛠 Tech Stack

- **Node.js**
- **Telegraf (Telegram Bot API)**
- **MongoDB + Mongoose**
- **Express**
- **Heroku**

---

## ⚙️ Environment Variables

Set these variables in Heroku or `.env`:

```env
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
MONGO_URI=YOUR_MONGODB_CONNECTION_STRING
OWNER_ID=YOUR_TELEGRAM_USER_ID

🚀 Deploy to Heroku
Click the button below to deploy instantly 👇

📂 Project Structure (Overview)

src/
 ├── server.js        # Express + MongoDB bootstrap
 ├── bot.js           # Bot commands & handlers
 ├── handlers/        # Command logic
 ├── models/          # MongoDB schemas
 ├── utils/           # XP system, dataset, i18n, moderation
 └── config/          # Owner configuration

👑 Credits
💡 Developed by Team BitCode
🤝 Telegram: @MR_CUTE_X
❤️ Open-source community support

📜 License
This project is licensed under the MIT License.
You are free to use, modify, and distribute it.

⭐ Support
If you like this project:
⭐ Star the repository
🍴 Fork it
📢 Share it with others

Happy coding 🚀

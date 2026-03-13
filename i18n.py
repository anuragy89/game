"""
i18n.py – Internationalization (English / Arabic / Hindi)
Usage:  from i18n import t
        t("welcome_dm", lang, name="Ahmed", users=1000, groups=50)
"""

STRINGS = {

# ──────────────────────────────────────────────────────────
"en": {
    "welcome_dm": (
        "👋 Hello, *{name}*!\n\n"
        "🎮 *XO Bot* — Tic-Tac-Toe for Telegram\n\n"
        "✨ *Features:*\n"
        "┣ ⚔️ PvP — Challenge your friends\n"
        "┣ 🤖 vs Bot — 3 difficulty levels\n"
        "┣ 🏆 Tournaments — Bracket system\n"
        "┣ 💰 Coins & Betting system\n"
        "┣ 🔥 Streaks & ELO rating\n"
        "┗ 📅 Daily challenges for free coins\n\n"
        "👥 *{users:,}* users  •  🏠 *{groups:,}* groups"
    ),
    "welcome_group": (
        "🎮 *XO Bot has entered the chat!*\n\n"
        "Play Tic-Tac-Toe right here — no links, no apps!\n\n"
        "┣ ⚔️ `/pvp @player` — Challenge someone\n"
        "┣ 🤖 `/pve` — Play vs AI bot\n"
        "┣ 🏆 `/tournament` — Start a bracket\n"
        "┣ 📅 `/daily` — Daily puzzle (+coins)\n"
        "┣ 💰 `/coins` — Your balance\n"
        "┣ 📊 `/stats` — Your stats\n"
        "┗ ❓ `/help` — All commands"
    ),
    "help": (
        "📖 *Help & Commands*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*🎮 Game*\n"
        "`/pvp @user` — Challenge a player\n"
        "`/pve` — Play vs AI bot\n"
        "`/accept` — Accept a challenge\n"
        "`/decline` — Decline a challenge\n"
        "`/board` — Redisplay the board\n"
        "`/quit` — Abandon current game\n\n"
        "*🏆 Tournament*\n"
        "`/tournament` — Start or join a bracket (4 or 8 players)\n\n"
        "*💰 Economy*\n"
        "`/coins` — Your coin balance\n"
        "`/bet <amount>` — Bet before a game\n"
        "`/daily` — Daily puzzle for free coins\n\n"
        "*📊 Stats*\n"
        "`/stats` — Wins, losses, ELO, streak\n"
        "`/top` — Global ELO leaderboard\n"
        "`/grouptop` — This group's top 10\n\n"
        "*⚙️ Settings*\n"
        "`/language` — Change language 🌐\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "_Bot difficulty: Easy / Medium / Hard (unbeatable Minimax AI)_"
    ),
    "your_turn":          "➡️ *Your turn!*",
    "bot_thinking":       "🤖 *Bot is thinking...*",
    "game_started":       "🎮 *Game started!* Good luck!",
    "you_are_x":          "You are ❌ — make the first move!",
    "win":                "🏆 *{name}* wins! {mark}",
    "draw":               "🤝 *It's a Draw!*",
    "not_your_turn":      "⏳ It's not your turn!",
    "not_in_game":        "You're not in this game!",
    "cell_taken":         "That cell is already taken!",
    "game_running":       "⚠️ A game is already running here! Use /quit to end it first.",
    "no_game":            "No active game! Start one with /pvp @user or /pve",
    "quit_msg":           "🏳️ {name} quit the game.",
    "challenge_sent":     "⚔️ {challenger} challenges {target}!\n\nTap a button to respond: ❌ vs ⭕",
    "challenge_expired":  "❌ This challenge has expired.",
    "cant_self":          "You can't challenge yourself! 😄",
    "pvp_dm_only":        "⚠️ PvP mode only works in groups! Add me to a group first.",
    "choose_difficulty":  "🤖 *Player vs Bot*\n\n{name}, choose difficulty level:",
    "only_challenger":    "Only the challenger can pick the difficulty!",
    "elo_change":         "📈 *{name}* ELO: {before} → {after} ({delta:+d})",
    "coins_earned_win":   "💰 *{name}* earned *+{amount} coins!*",
    "coins_earned_draw":  "💰 Both players earned *+{amount} coins!*",
    "streak_msg":         "🔥 *{name}* is on a *{streak}-win streak!*",
    "streak_broken":      "💔 *{name}*'s {streak}-win streak is broken!",
    "milestone_10":       "🎉 *{name}* just hit *10 wins* in this group! Legend! 🏆",
    "milestone_25":       "🌟 *{name}* smashed *25 wins* in this group! Unstoppable! 💪",
    "milestone_50":       "👑 *{name}* reached *50 wins* in this group! Absolute GOD! 🔥",
    "milestone_100":      "🚀 *{name}* achieved *100 wins* in this group! HALL OF FAME! 🏅",
    "daily_title":        "📅 *Daily Challenge*",
    "daily_done":         "✅ You've already completed today's challenge!\nCome back tomorrow for a new puzzle! 🌅",
    "daily_reward":       "🎉 *Correct!* You earned *+{coins} coins!*",
    "daily_fail":         "❌ Wrong move!\n\nThe winning move was cell *#{cell}*.\nBetter luck tomorrow! 💪",
    "no_coins":           "💸 Not enough coins!\nYour balance: *{balance} coins*",
    "bet_placed":         "💰 Bet of *{amount} coins* placed!\nWinner takes the pot! 🎯",
    "bet_won":            "💰 Bet won! *+{amount} coins* 🎉",
    "bet_lost":           "💸 Bet lost! *-{amount} coins*",
    "balance":            "💰 Your balance: *{balance} coins*",
    "lang_changed":       "✅ Language set to *English*!",
},

# ──────────────────────────────────────────────────────────
"ar": {
    "welcome_dm": (
        "👋 مرحباً، *{name}*!\n\n"
        "🎮 *XO Bot* — لعبة إكس-أو على تيليغرام\n\n"
        "✨ *المميزات:*\n"
        "┣ ⚔️ لاعب ضد لاعب\n"
        "┣ 🤖 لاعب ضد البوت (3 مستويات)\n"
        "┣ 🏆 بطولات بنظام الأدوار\n"
        "┣ 💰 نظام العملات والرهانات\n"
        "┣ 🔥 سلاسل الفوز وتقييم ELO\n"
        "┗ 📅 تحديات يومية للعملات المجانية\n\n"
        "👥 *{users:,}* مستخدم  •  🏠 *{groups:,}* مجموعة"
    ),
    "welcome_group": (
        "🎮 *XO Bot وصل للمجموعة!*\n\n"
        "العب إكس-أو هنا مباشرة!\n\n"
        "┣ ⚔️ `/pvp @player` — تحدي لاعب\n"
        "┣ 🤖 `/pve` — العب ضد البوت\n"
        "┣ 🏆 `/tournament` — ابدأ بطولة\n"
        "┣ 📅 `/daily` — تحدي يومي (+عملات)\n"
        "┣ 💰 `/coins` — رصيدك\n"
        "┣ 📊 `/stats` — إحصائياتك\n"
        "┗ ❓ `/help` — جميع الأوامر"
    ),
    "help": (
        "📖 *المساعدة والأوامر*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*🎮 اللعبة*\n"
        "`/pvp @user` — تحدي لاعب\n"
        "`/pve` — العب ضد البوت\n"
        "`/accept` — قبول التحدي\n"
        "`/decline` — رفض التحدي\n"
        "`/board` — عرض اللوحة\n"
        "`/quit` — الخروج من اللعبة\n\n"
        "*🏆 البطولة*\n"
        "`/tournament` — ابدأ أو انضم (4 أو 8 لاعبين)\n\n"
        "*💰 الاقتصاد*\n"
        "`/coins` — رصيدك\n"
        "`/bet <مبلغ>` — راهن قبل اللعبة\n"
        "`/daily` — تحدي يومي مجاني\n\n"
        "*📊 الإحصاء*\n"
        "`/stats` — إحصائياتك وELO\n"
        "`/top` — أفضل 10 عالمياً\n"
        "`/grouptop` — أفضل 10 في المجموعة\n\n"
        "*⚙️ الإعدادات*\n"
        "`/language` — تغيير اللغة 🌐\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    ),
    "your_turn":          "➡️ *دورك!*",
    "bot_thinking":       "🤖 *البوت يفكر...*",
    "game_started":       "🎮 *بدأت اللعبة!* حظاً موفقاً!",
    "you_are_x":          "أنت ❌ — ابدأ أول حركة!",
    "win":                "🏆 *{name}* فاز! {mark}",
    "draw":               "🤝 *تعادل!*",
    "not_your_turn":      "⏳ ليس دورك!",
    "not_in_game":        "أنت لست في هذه اللعبة!",
    "cell_taken":         "هذه الخانة مشغولة!",
    "game_running":       "⚠️ توجد لعبة جارية! استخدم /quit أولاً.",
    "no_game":            "لا توجد لعبة! ابدأ بـ /pvp @user أو /pve",
    "quit_msg":           "🏳️ {name} خرج من اللعبة.",
    "challenge_sent":     "⚔️ {challenger} يتحدى {target}!\n\naضغط للرد: ❌ vs ⭕",
    "challenge_expired":  "❌ انتهت صلاحية التحدي.",
    "cant_self":          "لا يمكنك تحدي نفسك! 😄",
    "pvp_dm_only":        "⚠️ PvP يعمل في المجموعات فقط! أضفني لمجموعة أولاً.",
    "choose_difficulty":  "🤖 *لاعب ضد البوت*\n\n{name}، اختر مستوى الصعوبة:",
    "only_challenger":    "فقط من أرسل التحدي يمكنه اختيار الصعوبة!",
    "elo_change":         "📈 *{name}* ELO: {before} → {after} ({delta:+d})",
    "coins_earned_win":   "💰 *{name}* كسب *+{amount} عملة!*",
    "coins_earned_draw":  "💰 كلا اللاعبين كسبا *+{amount} عملة!*",
    "streak_msg":         "🔥 *{name}* لديه *{streak} انتصارات متتالية!*",
    "streak_broken":      "💔 سلسلة انتصارات *{name}* ({streak}) انقطعت!",
    "milestone_10":       "🎉 *{name}* وصل لـ *10 انتصارات* في المجموعة! أسطورة! 🏆",
    "milestone_25":       "🌟 *{name}* حطم *25 انتصاراً*! لا يُوقف! 💪",
    "milestone_50":       "👑 *{name}* وصل لـ *50 انتصاراً*! إله! 🔥",
    "milestone_100":      "🚀 *{name}* حقق *100 انتصار*! 🏅",
    "daily_title":        "📅 *التحدي اليومي*",
    "daily_done":         "✅ أكملت تحدي اليوم! عد غداً! 🌅",
    "daily_reward":       "🎉 *صحيح!* ربحت *+{coins} عملة!*",
    "daily_fail":         "❌ إجابة خاطئة!\n\nالصحيح كان الخانة *#{cell}*.\nحظ أوفر غداً! 💪",
    "no_coins":           "💸 عملاتك غير كافية!\nرصيدك: *{balance} عملة*",
    "bet_placed":         "💰 رهان *{amount} عملة* تم! الفائز يأخذ الكل! 🎯",
    "bet_won":            "💰 ربحت الرهان! *+{amount} عملة* 🎉",
    "bet_lost":           "💸 خسرت الرهان! *-{amount} عملة*",
    "balance":            "💰 رصيدك: *{balance} عملة*",
    "lang_changed":       "✅ تم تغيير اللغة إلى *العربية*!",
},

# ──────────────────────────────────────────────────────────
"hi": {
    "welcome_dm": (
        "👋 नमस्ते, *{name}*!\n\n"
        "🎮 *XO Bot* — Telegram के लिए Tic-Tac-Toe\n\n"
        "✨ *खूबियाँ:*\n"
        "┣ ⚔️ PvP — दोस्तों को चुनौती दें\n"
        "┣ 🤖 vs Bot — 3 कठिनाई स्तर\n"
        "┣ 🏆 टूर्नामेंट — ब्रैकेट सिस्टम\n"
        "┣ 💰 कॉइन और बेटिंग सिस्टम\n"
        "┣ 🔥 स्ट्रीक और ELO रेटिंग\n"
        "┗ 📅 फ्री कॉइन के लिए डेली चैलेंज\n\n"
        "👥 *{users:,}* यूज़र  •  🏠 *{groups:,}* ग्रुप"
    ),
    "welcome_group": (
        "🎮 *XO Bot आ गया!*\n\n"
        "सीधे यहाँ Tic-Tac-Toe खेलें!\n\n"
        "┣ ⚔️ `/pvp @player` — किसी को चुनौती दें\n"
        "┣ 🤖 `/pve` — Bot से खेलें\n"
        "┣ 🏆 `/tournament` — टूर्नामेंट शुरू करें\n"
        "┣ 📅 `/daily` — डेली चैलेंज (+कॉइन)\n"
        "┣ 💰 `/coins` — आपका बैलेंस\n"
        "┣ 📊 `/stats` — आपके आँकड़े\n"
        "┗ ❓ `/help` — सभी कमांड"
    ),
    "help": (
        "📖 *सहायता और कमांड*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*🎮 गेम*\n"
        "`/pvp @user` — खिलाड़ी को चुनौती\n"
        "`/pve` — Bot से खेलें\n"
        "`/accept` — चुनौती स्वीकार\n"
        "`/decline` — चुनौती अस्वीकार\n"
        "`/board` — बोर्ड दिखाएँ\n"
        "`/quit` — गेम छोड़ें\n\n"
        "*🏆 टूर्नामेंट*\n"
        "`/tournament` — शुरू/जॉइन करें (4 या 8 खिलाड़ी)\n\n"
        "*💰 इकॉनमी*\n"
        "`/coins` — आपका बैलेंस\n"
        "`/bet <राशि>` — गेम से पहले बेट\n"
        "`/daily` — डेली चैलेंज (+कॉइन)\n\n"
        "*📊 आँकड़े*\n"
        "`/stats` — जीत/हार/ELO/स्ट्रीक\n"
        "`/top` — ग्लोबल टॉप 10\n"
        "`/grouptop` — इस ग्रुप का टॉप 10\n\n"
        "*⚙️ सेटिंग्स*\n"
        "`/language` — भाषा बदलें 🌐\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    ),
    "your_turn":          "➡️ *आपकी बारी!*",
    "bot_thinking":       "🤖 *Bot सोच रहा है...*",
    "game_started":       "🎮 *गेम शुरू!* शुभकामनाएँ!",
    "you_are_x":          "आप ❌ हैं — पहली चाल चलें!",
    "win":                "🏆 *{name}* जीत गया! {mark}",
    "draw":               "🤝 *ड्रॉ!*",
    "not_your_turn":      "⏳ अभी आपकी बारी नहीं है!",
    "not_in_game":        "आप इस गेम में नहीं हैं!",
    "cell_taken":         "यह सेल भरा हुआ है!",
    "game_running":       "⚠️ गेम चल रहा है! पहले /quit करें।",
    "no_game":            "कोई गेम नहीं! /pvp @user या /pve से शुरू करें",
    "quit_msg":           "🏳️ {name} ने गेम छोड़ दिया।",
    "challenge_sent":     "⚔️ {challenger} ने {target} को चुनौती दी!\n\nजवाब देने के लिए टैप करें: ❌ vs ⭕",
    "challenge_expired":  "❌ यह चुनौती समाप्त हो गई।",
    "cant_self":          "खुद को चुनौती नहीं दे सकते! 😄",
    "pvp_dm_only":        "⚠️ PvP ग्रुप के लिए है! पहले मुझे ग्रुप में जोड़ें।",
    "choose_difficulty":  "🤖 *खिलाड़ी vs Bot*\n\n{name}, कठिनाई स्तर चुनें:",
    "only_challenger":    "केवल चुनौती देने वाला कठिनाई चुन सकता है!",
    "elo_change":         "📈 *{name}* ELO: {before} → {after} ({delta:+d})",
    "coins_earned_win":   "💰 *{name}* को *+{amount} कॉइन* मिले!",
    "coins_earned_draw":  "💰 दोनों खिलाड़ियों को *+{amount} कॉइन* मिले!",
    "streak_msg":         "🔥 *{name}* की *{streak} जीत की लकीर!*",
    "streak_broken":      "💔 *{name}* की {streak}-जीत की लकीर टूट गई!",
    "milestone_10":       "🎉 *{name}* ने इस ग्रुप में *10 जीत* हासिल की! लीजेंड! 🏆",
    "milestone_25":       "🌟 *{name}* ने *25 जीत* तोड़ी! अजेय! 💪",
    "milestone_50":       "👑 *{name}* ने *50 जीत* छुई! देवता! 🔥",
    "milestone_100":      "🚀 *{name}* ने *100 जीत* हासिल की! 🏅",
    "daily_title":        "📅 *डेली चैलेंज*",
    "daily_done":         "✅ आज का चैलेंज पूरा हो गया!\nकल वापस आएँ! 🌅",
    "daily_reward":       "🎉 *सही!* आपको *+{coins} कॉइन* मिले!",
    "daily_fail":         "❌ गलत चाल!\n\nसही जवाब था सेल *#{cell}*।\nकल बेहतर करें! 💪",
    "no_coins":           "💸 पर्याप्त कॉइन नहीं!\nबैलेंस: *{balance} कॉइन*",
    "bet_placed":         "💰 *{amount} कॉइन* की बेट लगी! जीतने वाला सब लेगा! 🎯",
    "bet_won":            "💰 बेट जीती! *+{amount} कॉइन* 🎉",
    "bet_lost":           "💸 बेट हारी! *-{amount} कॉइन*",
    "balance":            "💰 आपका बैलेंस: *{balance} कॉइन*",
    "lang_changed":       "✅ भाषा *हिंदी* में सेट की गई!",
},

}


def t(key: str, lang: str = "en", **kwargs) -> str:
    """
    Translate key in given language with optional format args.
    Falls back to English if key or language not found.
    """
    lang_strings = STRINGS.get(lang, STRINGS["en"])
    template = lang_strings.get(key) or STRINGS["en"].get(key, key)
    try:
        return template.format(**kwargs) if kwargs else template
    except (KeyError, IndexError):
        return template

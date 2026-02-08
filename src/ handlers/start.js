const User = require("../models/User");

module.exports = async (ctx) => {
  await User.updateOne(
    { userId: ctx.from.id },
    { $setOnInsert: { username: ctx.from.username } },
    { upsert: true }
  );

  ctx.reply(
    "🎭 *Truth & Dare Bot*\n\nPlay fun games in groups 🚀",
    {
      parse_mode: "Markdown",
      reply_markup: {
        inline_keyboard: [
          [{ text: "🆘 Help", callback_data: "help" }],
          [{ text: "📢 Updates", url: "https://t.me/MR_CUTE_X" }]
        ]
      }
    }
  );
};

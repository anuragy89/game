const User = require("../models/User");

module.exports = async (ctx) => {
  const users = await User.find().sort({ xp: -1 }).limit(10);
  if (!users.length) return ctx.reply("No players yet");

  let text = "🏆 *Leaderboard*\n\n";
  users.forEach((u, i) => {
    text += `${i + 1}. ${u.username || u.userId} — ${u.xp} XP\n`;
  });

  ctx.reply(text, { parse_mode: "Markdown" });
};

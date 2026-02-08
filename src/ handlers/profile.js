const User = require("../models/User");
const { calculateLevel } = require("../utils/levels");

module.exports = async (ctx) => {
  const u = await User.findOne({ userId: ctx.from.id });
  if (!u) return ctx.reply("No profile");

  ctx.reply(
    `👤 *Profile*\n⭐ XP: ${u.xp}\n🎯 Level: ${calculateLevel(u.xp)}`,
    { parse_mode: "Markdown" }
  );
};

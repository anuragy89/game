const User = require("../models/User");

module.exports = async (ctx) => {
  const user = await User.findOne({ userId: ctx.from.id }) || new User({ userId: ctx.from.id });

  if (user.lastDaily && Date.now() - user.lastDaily < 86400000) {
    return ctx.reply("⏳ Come back tomorrow");
  }

  user.xp += 50;
  user.lastDaily = new Date();
  await user.save();

  ctx.reply("🎁 You received *50 XP*", { parse_mode: "Markdown" });
};

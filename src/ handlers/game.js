const User = require("../models/User");
const Group = require("../models/Group");
const data = require("../utils/dataset");
const { calculateLevel } = require("../utils/levels");

module.exports = async (ctx, type) => {
  if (ctx.chat.type === "private") {
    return ctx.reply("👥 Use this in a group");
  }

  const question = data[type][Math.floor(Math.random() * data[type].length)];

  let user = await User.findOne({ userId: ctx.from.id });
  if (!user) user = new User({ userId: ctx.from.id, username: ctx.from.username });

  const oldLevel = calculateLevel(user.xp);
  user.xp += 10;
  await user.save();

  const newLevel = calculateLevel(user.xp);

  await Group.updateOne(
    { groupId: ctx.chat.id },
    { $inc: { "stats.games": 1, [`stats.${type}`]: 1 } },
    { upsert: true }
  );

  let msg = `🎯 *${type.toUpperCase()}*\n\n${question}`;
  if (newLevel > oldLevel) msg += `\n\n🎉 *LEVEL UP!* Level ${newLevel}`;

  ctx.reply(msg, { parse_mode: "Markdown" });
};

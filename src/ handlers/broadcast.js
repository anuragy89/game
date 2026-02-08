const User = require("../models/User");
const Group = require("../models/Group");
const { OWNER_ID } = require("../config/owner");

module.exports = async (ctx) => {
  if (ctx.from.id !== OWNER_ID) return ctx.reply("🚫 Owner only");

  const text = ctx.message.text.replace("/broadcast", "").trim();
  if (!text) return ctx.reply("Usage: /broadcast message");

  const users = await User.find();
  const groups = await Group.find();

  for (const u of users) {
    try { await ctx.telegram.sendMessage(u.userId, text); } catch {}
  }
  for (const g of groups) {
    try { await ctx.telegram.sendMessage(g.groupId, text); } catch {}
  }

  ctx.reply("✅ Broadcast sent");
};

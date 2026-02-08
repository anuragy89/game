const Group = require("../models/Group");

module.exports = async (ctx) => {
  if (ctx.chat.type === "private") return ctx.reply("Group only");

  const g = await Group.findOne({ groupId: ctx.chat.id });
  if (!g) return ctx.reply("No stats yet");

  ctx.reply(
    `📊 *Group Stats*\n🎮 Games: ${g.stats.games}\n🤔 Truth: ${g.stats.truth}\n🔥 Dare: ${g.stats.dare}`,
    { parse_mode: "Markdown" }
  );
};

const rules = require("../utils/moderationRules");
const cache = new Map();

module.exports = async (ctx) => {
  if (!ctx.message?.text || ctx.chat.type === "private") return;

  const now = Date.now();
  const key = `${ctx.chat.id}:${ctx.from.id}`;
  const arr = cache.get(key) || [];
  const recent = arr.filter(t => now - t < rules.flood.intervalMs);
  recent.push(now);
  cache.set(key, recent);

  if (recent.length > rules.flood.maxMessages) {
    await ctx.deleteMessage();
    return ctx.reply("⚠️ Slow down");
  }

  if (rules.bannedWords.some(w => ctx.message.text.toLowerCase().includes(w))) {
    await ctx.deleteMessage();
    return ctx.reply("🚫 Message removed");
  }
};

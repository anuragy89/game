module.exports = (bot) => {
  bot.start(async (ctx) => {
    const name = ctx.from.first_name || "there";

    await ctx.reply(
      `👋 Hello ${name}!\n\n🎮 Welcome to *Truth & Dare Game Bot*\n\nUse /help to see commands.`,
      {
        parse_mode: "Markdown"
      }
    );
  });
};

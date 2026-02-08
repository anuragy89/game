module.exports = (ctx) => {
  ctx.reply(
    "🆘 *Commands*\n\n" +
    "/truth – Truth\n" +
    "/dare – Dare\n" +
    "/profile – Profile\n" +
    "/leaderboard – Top players\n" +
    "/daily – Daily reward\n" +
    "/analytics – Group stats",
    { parse_mode: "Markdown" }
  );
};

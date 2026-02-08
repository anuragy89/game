const { Telegraf } = require("telegraf");

const start = require("./handlers/start");
const help = require("./handlers/help");
const game = require("./handlers/game");
const leaderboard = require("./handlers/leaderboard");
const profile = require("./handlers/profile");
const daily = require("./handlers/daily");
const analytics = require("./handlers/analytics");
const broadcast = require("./handlers/broadcast");
const moderation = require("./handlers/moderation");

const bot = new Telegraf(process.env.BOT_TOKEN);

bot.start(start);
bot.command("help", help);
bot.command("truth", ctx => game(ctx, "truth"));
bot.command("dare", ctx => game(ctx, "dare"));
bot.command("leaderboard", leaderboard);
bot.command("profile", profile);
bot.command("daily", daily);
bot.command("analytics", analytics);
bot.command("broadcast", broadcast);

bot.on("message", moderation);

module.exports = bot;

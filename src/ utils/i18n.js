/**
 * Simple i18n system
 * Easily expandable for more languages
 */

const messages = {
  en: {
    start:
      "🎭 *Truth & Dare Bot*\n\nPlay fun games in groups and earn XP 🚀",

    help:
      "🆘 *Available Commands*\n\n" +
      "/truth – Truth question 🤔\n" +
      "/dare – Dare challenge 🔥\n" +
      "/profile – Your profile 👤\n" +
      "/leaderboard – Top players 🏆\n" +
      "/daily – Daily reward 🎁\n" +
      "/analytics – Group stats 📊",

    levelUp: (level) =>
      `🎉 *LEVEL UP!*\nYou reached *Level ${level}* 🚀`
  },

  hi: {
    start:
      "🎭 *ट्रुथ एंड डेयर बॉट*\n\nग्रुप में खेलें और XP कमाएँ 🚀",

    help:
      "🆘 *कमांड सूची*\n\n" +
      "/truth – ट्रुथ 🤔\n" +
      "/dare – डेयर 🔥\n" +
      "/profile – प्रोफ़ाइल 👤\n" +
      "/leaderboard – टॉप खिलाड़ी 🏆\n" +
      "/daily – डेली रिवॉर्ड 🎁\n" +
      "/analytics – ग्रुप स्टैट्स 📊",

    levelUp: (level) =>
      `🎉 *लेवल अप!*\nआप लेवल ${level} पर पहुँच गए 🚀`
  }
};

/**
 * Translation helper
 */
exports.t = (lang, key, data) => {
  const language = messages[lang] ? lang : "en";
  const value = messages[language][key];

  if (typeof value === "function") {
    return value(data);
  }

  return value || messages.en[key] || "";
};

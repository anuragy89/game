exports.calculateLevel = (xp) => {
  let level = 1;
  let required = 100;

  while (xp >= required) {
    level++;
    required += level * 100;
  }

  return level;
};

const mongoose = require("mongoose");

const GroupSchema = new mongoose.Schema({
  groupId: { type: Number, unique: true },
  stats: {
    games: { type: Number, default: 0 },
    truth: { type: Number, default: 0 },
    dare: { type: Number, default: 0 },
    messages: { type: Number, default: 0 }
  },
  lastActive: Date
});

module.exports = mongoose.model("Group", GroupSchema);

const mongoose = require("mongoose");

const UserSchema = new mongoose.Schema({
  userId: { type: Number, unique: true },
  username: String,
  xp: { type: Number, default: 0 },
  language: { type: String, default: "en" },
  referrals: { type: Number, default: 0 },
  lastDaily: Date
});

module.exports = mongoose.model("User", UserSchema);

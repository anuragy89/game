require("dotenv").config();
const express = require("express");
const mongoose = require("mongoose");
const bot = require("./bot");

const app = express();

mongoose.connect(process.env.MONGO_URI)
  .then(() => {
    console.log("✅ MongoDB Connected");
    bot.launch();
  })
  .catch(err => {
    console.error("❌ Mongo Error", err);
    process.exit(1);
  });

app.get("/", (_, res) => res.send("🤖 Bot Running"));
app.listen(process.env.PORT || 3000);

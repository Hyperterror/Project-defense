const express = require("express");
const cors = require("cors");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const mongoose = require("mongoose");
const authMiddleware = require("./middleware/auth");
const todoRoutes = require("./routes/todos");
const authRoutes = require("./routes/auth");

const app = express();

app.use(cors());
app.use(express.json());

// Auth endpoints (public)
app.use("/api/auth", authRoutes);

// Todo endpoints (protected)
app.use("/api/todos", authMiddleware, todoRoutes);

// Health check
app.get("/api/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: "Not found" });
});

// Error handler
app.use((err, req, res, next) => {
  console.error(err.stack);
  res.status(500).json({ error: "Internal server error" });
});

const PORT = process.env.PORT || 3000;
const MONGODB_URI = process.env.MONGODB_URI || "mongodb://localhost:27017/todoapp";

mongoose
  .connect(MONGODB_URI)
  .then(() => {
    app.listen(PORT, () => console.log(`Server listening on ${PORT}`));
  })
  .catch((err) => console.error("MongoDB connection failed:", err));

module.exports = app;

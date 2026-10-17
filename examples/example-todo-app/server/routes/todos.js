const express = require("express");
const Todo = require("../models/Todo");

const router = express.Router();

router.get("/", async (req, res) => {
  const todos = await Todo.find({ userId: req.user.id }).sort({ createdAt: -1 });
  res.json(todos);
});

router.post("/", async (req, res) => {
  const { title } = req.body;
  if (!title || typeof title !== "string") {
    return res.status(400).json({ error: "Title is required and must be a string" });
  }
  const todo = await Todo.create({ title, userId: req.user.id, completed: false });
  res.status(201).json(todo);
});

router.patch("/:id", async (req, res) => {
  const { id } = req.params;
  const { completed } = req.body;
  const todo = await Todo.findOneAndUpdate(
    { _id: id, userId: req.user.id },
    { completed },
    { new: true }
  );
  if (!todo) {
    return res.status(404).json({ error: "Todo not found" });
  }
  res.json(todo);
});

router.delete("/:id", async (req, res) => {
  const { id } = req.params;
  const result = await Todo.findOneAndDelete({ _id: id, userId: req.user.id });
  if (!result) {
    return res.status(404).json({ error: "Todo not found" });
  }
  res.status(204).send();
});

module.exports = router;

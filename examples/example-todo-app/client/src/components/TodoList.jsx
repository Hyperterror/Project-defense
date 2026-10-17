import React, { useState, useEffect } from "react";
import axios from "axios";
import TodoItem from "./TodoItem";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:3000";

function TodoList({ token, onLogout }) {
  const [todos, setTodos] = useState([]);
  const [newTitle, setNewTitle] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchTodos = async () => {
      try {
        setLoading(true);
        const res = await axios.get(`${API_URL}/api/todos`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        setTodos(res.data);
      } catch (err) {
        setError(err.response?.data?.error || "Failed to load todos");
        if (err.response?.status === 401) onLogout();
      } finally {
        setLoading(false);
      }
    };
    fetchTodos();
  }, [token, onLogout]);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      const res = await axios.post(
        `${API_URL}/api/todos`,
        { title: newTitle },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setTodos([res.data, ...todos]);
      setNewTitle("");
    } catch (err) {
      setError(err.response?.data?.error || "Failed to add todo");
    }
  };

  const handleToggle = async (id, completed) => {
    try {
      const res = await axios.patch(
        `${API_URL}/api/todos/${id}`,
        { completed },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setTodos(todos.map((t) => (t._id === id ? res.data : t)));
    } catch (err) {
      setError(err.response?.data?.error || "Failed to update todo");
    }
  };

  const handleDelete = async (id) => {
    try {
      await axios.delete(`${API_URL}/api/todos/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setTodos(todos.filter((t) => t._id !== id));
    } catch (err) {
      setError(err.response?.data?.error || "Failed to delete todo");
    }
  };

  return (
    <div className="todo-list">
      <h1>My Todos</h1>
      <button onClick={onLogout}>Log out</button>
      <form onSubmit={handleAdd}>
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="What needs doing?"
        />
        <button type="submit">Add</button>
      </form>
      {error && <div className="error">{error}</div>}
      {loading ? (
        <div>Loading...</div>
      ) : (
        todos.map((todo) => (
          <TodoItem
            key={todo._id}
            todo={todo}
            onToggle={handleToggle}
            onDelete={handleDelete}
          />
        ))
      )}
    </div>
  );
}

export default TodoList;

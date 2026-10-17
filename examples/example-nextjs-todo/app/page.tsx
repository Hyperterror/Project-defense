"use client";
import { useEffect, useState } from "react";

export default function TodoList() {
  const [todos, setTodos] = useState<{ id: string; title: string; completed: boolean }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");

  useEffect(() => {
    fetch("/api/todos")
      .then((r) => r.json())
      .then(setTodos)
      .catch((e) => setError(String(e)));
  }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch("/api/todos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle }),
    });
    const data = await res.json();
    setTodos([...todos, data]);
    setNewTitle("");
  };

  return (
    <div>
      <h1>Todos</h1>
      {error && <div className="error">{error}</div>}
      <form onSubmit={handleAdd}>
        <input value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
        <button type="submit">Add</button>
      </form>
      {todos.map((t) => (
        <div key={t.id}>{t.title}</div>
      ))}
    </div>
  );
}

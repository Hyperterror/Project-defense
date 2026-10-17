import React from "react";

function TodoItem({ todo, onToggle, onDelete }) {
  return (
    <div className="todo-item">
      <input
        type="checkbox"
        checked={todo.completed}
        onChange={(e) => onToggle(todo._id, e.target.checked)}
      />
      <span style={{ textDecoration: todo.completed ? "line-through" : "none" }}>
        {todo.title}
      </span>
      <button onClick={() => onDelete(todo._id)}>Delete</button>
    </div>
  );
}

export default TodoItem;

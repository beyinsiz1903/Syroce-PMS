import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import "@/i18n";
import App from "@/App";

if (import.meta.env.DEV) {
  const _origWarn = console.warn;
  console.warn = (...args) => {
    const msg = typeof args[0] === "string" ? args[0] : "";
    if (msg.includes("width(") && msg.includes("height(") && msg.includes("chart")) return;
    _origWarn.apply(console, args);
  };
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

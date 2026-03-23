import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import App from "@/App";
// Import i18n with error handling
import("./i18n").catch((error) => {
  console.warn("i18n initialization failed:", error);
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

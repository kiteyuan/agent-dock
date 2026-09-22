import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { ThemeRoot } from "./themeRoot";
import { applyDocumentTheme, readStoredTheme } from "./theme";
import "./theme.css";
import "./styles.css";

applyDocumentTheme(readStoredTheme());

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeRoot>
      <App />
    </ThemeRoot>
  </React.StrictMode>,
);

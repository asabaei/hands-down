import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
// fonts are bundled with the app (no requests to Google Fonts, works offline)
import "@fontsource-variable/nunito";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

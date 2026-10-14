import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/fraunces/full.css"; // all axes, incl. SOFT for the rounded headings
import "@fontsource-variable/jetbrains-mono";
import "@fontsource-variable/atkinson-hyperlegible-next";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

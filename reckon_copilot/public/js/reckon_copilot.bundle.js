import "../css/copilot.css";
import { mountCopilot } from "./copilot/main";

function ensureCopilotStyles() {
  const href = "/assets/reckon_copilot/css/copilot.css";
  const selector = `link[href="${href}"]`;
  if (document.querySelector(selector)) return;

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

ensureCopilotStyles();

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountCopilot, { once: true });
} else {
  mountCopilot();
}

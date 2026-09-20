import "../css/copilot.css";
import { mountCopilot } from "./copilot/main";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountCopilot, { once: true });
} else {
  mountCopilot();
}

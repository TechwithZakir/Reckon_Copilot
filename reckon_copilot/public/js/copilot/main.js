import { createApp, h, reactive } from "vue";
import Copilot from "./Copilot.vue";

const ROOT_ID = "reckon-copilot-root";

function getPageType() {
  const route = window.frappe?.get_route?.() || [];
  const routeType = route[0];
  if (["Form", "List", "Report", "Workspace"].includes(routeType)) {
    return routeType;
  }
  return "Page";
}

export function mountCopilot() {
  if (document.getElementById(ROOT_ID) || !document.body) return;

  const root = document.createElement("div");
  root.id = ROOT_ID;
  document.body.appendChild(root);

  const context = reactive({ pageType: getPageType() });
  window.frappe?.router?.on?.("change", () => {
    context.pageType = getPageType();
  });

  createApp({ render: () => h(Copilot, { pageType: context.pageType }) }).mount(root);
}

import { createApp, h, reactive } from "vue";
import Copilot from "./Copilot.vue";
import { getRouteContext } from "./api";
import { getCanonicalRoute, getPageType } from "./route_context.mjs";

const ROOT_ID = "reckon-copilot-root";

function getRouteFilters() {
  const query = window.frappe?.utils?.get_query_params?.() || {};
  return Object.fromEntries(
    Object.entries(query).filter(([key, value]) => {
      return key && value !== undefined && value !== null && String(value).length <= 160;
    }),
  );
}

export function mountCopilot() {
  if (document.getElementById(ROOT_ID) || !document.body) return;

  const root = document.createElement("div");
  root.id = ROOT_ID;
  document.body.appendChild(root);

  const context = reactive({
    pageType: getPageType(),
    routeContext: null,
  });

  let requestId = 0;

  async function syncContext() {
    const route = getCanonicalRoute();
    const currentRequest = ++requestId;
    context.pageType = getPageType(route);
    try {
      const routeContext = await getRouteContext(route, getRouteFilters(), context.pageType);
      if (currentRequest === requestId) {
        context.routeContext = routeContext;
        context.pageType = routeContext.page_type || context.pageType;
      }
    } catch (_error) {
      if (currentRequest === requestId) {
        context.routeContext = null;
      }
    }
  }

  function scheduleContextSync() {
    syncContext();
    window.setTimeout(syncContext, 150);
    window.setTimeout(syncContext, 500);
  }

  window.frappe?.router?.on?.("change", scheduleContextSync);
  window.addEventListener("popstate", syncContext);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) syncContext();
  });
  syncContext();

  createApp({
    render: () =>
      h(Copilot, {
        pageType: context.pageType,
        routeContext: context.routeContext,
      }),
  }).mount(root);
}

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

function fallbackPageContext(route) {
  const parts = Array.isArray(route) ? route : [];
  return {
    version: "v1",
    source: "desk_route",
    route: parts,
    page_type: "Page",
    page_name: parts.at(-1) || "Current page",
    permission: {
      mode: "generic_page_fallback",
      enforcement: "phase_3",
    },
  };
}

export function mountCopilot() {
  if (document.getElementById(ROOT_ID) || !document.body) return;

  const root = document.createElement("div");
  root.id = ROOT_ID;
  document.body.appendChild(root);

  const context = reactive({
    pageType: getPageType(),
    routeContext: null,
    contextAlert: "",
  });

  let requestId = 0;

  async function syncContext() {
    const route = getCanonicalRoute();
    const currentRequest = ++requestId;
    context.pageType = getPageType(route);
    try {
      const routeContext = await getRouteContext(route, getRouteFilters(), context.pageType);
      if (currentRequest === requestId) {
        if (routeContext?.permission?.context_fallback === "missing_doctype") {
          console.info(
            "[Reckon Copilot] Structured context skipped because the route is not a DocType page.",
            { route, page: routeContext.page_name },
          );
        }
        context.routeContext = routeContext;
        context.pageType = routeContext.page_type || context.pageType;
        context.contextAlert = routeContext.access_denied
          ? routeContext.permission?.reason ||
            "Copilot cannot access this page with your current permissions."
          : "";
      }
    } catch (error) {
      if (currentRequest === requestId) {
        context.routeContext = fallbackPageContext(route);
        context.pageType = "Page";
        context.contextAlert = "";
        console.warn(
          "[Reckon Copilot] Page context was unavailable; using generic page context.",
          { route, error },
        );
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
        contextAlert: context.contextAlert,
      }),
  }).mount(root);
}

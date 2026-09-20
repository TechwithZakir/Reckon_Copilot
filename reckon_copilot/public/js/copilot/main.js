import { createApp, h, reactive } from "vue";
import Copilot from "./Copilot.vue";
import { getRouteContext } from "./api";

const ROOT_ID = "reckon-copilot-root";

function getRoute() {
  return window.frappe?.get_route?.() || [];
}

function titleCaseSlug(value) {
  return String(value || "")
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getDeskSlug() {
  const match = window.location.pathname.match(/\/desk\/([^/?#]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function getCanonicalRoute(rawRoute = getRoute()) {
  if (window.cur_frm?.doctype) {
    return [
      "Form",
      window.cur_frm.doctype,
      window.cur_frm.doc?.name || rawRoute[2] || rawRoute[1],
    ].filter(Boolean);
  }

  if (window.cur_list?.doctype) {
    return ["List", window.cur_list.doctype, window.cur_list.view_name || "List"];
  }

  if (window.query_report?.report_name) {
    return ["Report", window.query_report.report_name];
  }

  const routeType = rawRoute[0];
  if (["Form", "List", "Report", "Dashboard", "Workspace"].includes(routeType)) {
    return rawRoute;
  }

  const slug = getDeskSlug() || routeType;
  if (!slug) return rawRoute;
  if (document.querySelector(".list-row-container, .list-header, .list-sidebar")) {
    return ["List", titleCaseSlug(slug), "List"];
  }
  if (document.querySelector(".workspace, .codex-editor, .widget-group")) {
    return ["Workspace", titleCaseSlug(slug)];
  }
  return rawRoute;
}

function getPageType(route = getRoute()) {
  const routeType = route[0];
  if (["Form", "List", "Report", "Dashboard", "Workspace"].includes(routeType)) {
    return routeType;
  }
  return "Page";
}

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

  window.frappe?.router?.on?.("change", syncContext);
  syncContext();

  createApp({
    render: () =>
      h(Copilot, {
        pageType: context.pageType,
        routeContext: context.routeContext,
      }),
  }).mount(root);
}

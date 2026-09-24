export function getRoute() {
  return window.frappe?.get_route?.() || [];
}

export function titleCaseSlug(value) {
  return String(value || "")
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function getDeskParts() {
  const match = window.location.pathname.match(/\/desk\/?([^?#]*)/);
  if (!match) return [];
  return match[1]
    .split("/")
    .filter(Boolean)
    .map((part) => decodeURIComponent(part));
}

export function slugify(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function pageTitle() {
  const title =
    document.querySelector(".page-title .title-text")?.textContent ||
    document.querySelector(".page-head .title-text")?.textContent ||
    document.querySelector(".navbar-breadcrumbs li:last-child a")?.textContent ||
    document.querySelector(".breadcrumb-item:last-child")?.textContent ||
    "";
  return title.trim();
}

function visibleListViewName() {
  const selected =
    document.querySelector(".btn-group .btn.btn-default.ellipsis")?.textContent ||
    document.querySelector(".standard-actions .btn-default")?.textContent ||
    "";
  return selected.trim();
}

function looksLikeDeskListPage(slug) {
  if (!slug) return false;
  if (document.querySelector(".layout-main-section .result, .list-row-container, .frappe-list")) {
    return true;
  }
  if (document.querySelector(".page-actions .primary-action, .standard-actions .primary-action")) {
    return true;
  }
  const title = pageTitle();
  return Boolean(title && slugify(title) === slug);
}

export function getCanonicalRoute(rawRoute = getRoute()) {
  const deskParts = getDeskParts();
  const slug = deskParts[0] || "";

  if (deskParts.length === 0) {
    return ["Homepage", "Home"];
  }

  if (slug === "dashboard-view") {
    return ["Dashboard", titleCaseSlug(deskParts[1] || rawRoute[1] || "Dashboard")];
  }

  if (slug === "query-report") {
    return ["Report", window.query_report?.report_name || deskParts[1] || rawRoute[1]].filter(Boolean);
  }

  if (
    window.cur_frm?.doctype &&
    (rawRoute[0] === "Form" || (deskParts.length > 1 && slugify(window.cur_frm.doctype) === slug))
  ) {
    return [
      "Form",
      window.cur_frm.doctype,
      window.cur_frm.doc?.name || rawRoute[2] || rawRoute[1] || deskParts[1],
    ].filter(Boolean);
  }

  if (window.cur_list?.doctype && slugify(window.cur_list.doctype) === slug) {
    return ["List", window.cur_list.doctype, window.cur_list.view_name || "List"];
  }

  if (window.query_report?.report_name) {
    return ["Report", window.query_report.report_name];
  }

  const routeType = rawRoute[0];
  if (["Form", "List", "Report", "Dashboard", "Workspace", "Homepage"].includes(routeType)) {
    return rawRoute;
  }

  if (deskParts.length === 1 && looksLikeDeskListPage(slug)) {
    return ["List", pageTitle() || titleCaseSlug(slug), visibleListViewName() || "List"];
  }

  if (document.querySelector(".workspace, .codex-editor, .widget-group")) {
    return ["Workspace", titleCaseSlug(slug)];
  }
  if (slug) {
    return ["Workspace", titleCaseSlug(slug)];
  }
  return rawRoute;
}

export function getPageType(route = getRoute()) {
  const routeType = route[0];
  if (["Form", "List", "Report", "Dashboard", "Workspace", "Homepage"].includes(routeType)) {
    return routeType;
  }
  return "Page";
}

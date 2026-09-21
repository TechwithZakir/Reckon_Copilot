import assert from "node:assert/strict";
import test from "node:test";

import { getCanonicalRoute, getPageType } from "./route_context.mjs";

function setDeskPath(pathname) {
  const selectors = new Map();
  global.window = {
    location: { pathname },
    frappe: { get_route: () => [] },
  };
  global.document = {
    querySelector: (selector) => selectors.get(selector) || null,
    addEventListener: () => null,
    hidden: false,
    selectors,
  };
  delete global.window.cur_frm;
  delete global.window.cur_list;
  delete global.window.query_report;
}

function textNode(textContent) {
  return { textContent };
}

test("desk home is normalized as workspace home", () => {
  setDeskPath("/desk");

  const route = getCanonicalRoute([]);

  assert.deepEqual(route, ["Workspace", "Home"]);
  assert.equal(getPageType(route), "Workspace");
});

test("dashboard-view route is normalized as dashboard", () => {
  setDeskPath("/desk/dashboard-view/Selling");

  const route = getCanonicalRoute(["dashboard-view", "Selling"]);

  assert.deepEqual(route, ["Dashboard", "Selling"]);
  assert.equal(getPageType(route), "Dashboard");
});

test("module workspace route is not promoted to list by list-like dom", () => {
  setDeskPath("/desk/projects");
  global.document.querySelector = (selector) => {
    return selector.includes("list-sidebar") ? {} : null;
  };

  const route = getCanonicalRoute(["projects"]);

  assert.deepEqual(route, ["Workspace", "Projects"]);
  assert.equal(getPageType(route), "Workspace");
});

test("one-part doctype route falls back to visible title before cur_list is ready", () => {
  setDeskPath("/desk/customer-group");
  global.document.selectors.set(".page-title .title-text", textNode("Customer Group"));
  global.document.selectors.set(".page-actions .primary-action, .standard-actions .primary-action", {});

  const route = getCanonicalRoute(["customer-group"]);

  assert.deepEqual(route, ["List", "Customer Group", "List"]);
  assert.equal(getPageType(route), "List");
});

test("query-report route beats stale form state", () => {
  setDeskPath("/desk/query-report/Project%20Summary");
  global.window.cur_frm = {
    doctype: "Project",
    doc: { name: "PROJ-0001" },
  };

  const route = getCanonicalRoute(["query-report", "Project Summary"]);

  assert.deepEqual(route, ["Report", "Project Summary"]);
  assert.equal(getPageType(route), "Report");
});

test("stale form global does not turn a one-part list route into form", () => {
  setDeskPath("/desk/sales-order");
  global.window.cur_frm = {
    doctype: "Sales Order",
    doc: { name: "new-sales-order" },
  };
  global.window.cur_list = {
    doctype: "Sales Order",
    view_name: "List",
  };

  const route = getCanonicalRoute(["sales-order"]);

  assert.deepEqual(route, ["List", "Sales Order", "List"]);
  assert.equal(getPageType(route), "List");
});

test("two-part desk document route is normalized as form", () => {
  setDeskPath("/desk/quotation/new-quotation-ddqhbpfyym");
  global.window.cur_frm = {
    doctype: "Quotation",
    doc: { name: "new-quotation-ddqhbpfyym" },
  };

  const route = getCanonicalRoute(["quotation", "new-quotation-ddqhbpfyym"]);

  assert.deepEqual(route, ["Form", "Quotation", "new-quotation-ddqhbpfyym"]);
  assert.equal(getPageType(route), "Form");
});

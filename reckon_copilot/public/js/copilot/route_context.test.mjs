import assert from "node:assert/strict";
import test from "node:test";

import { getCanonicalRoute, getPageType } from "./route_context.mjs";

function setDeskPath(pathname) {
  global.window = {
    location: { pathname },
    frappe: { get_route: () => [] },
  };
  global.document = {
    querySelector: () => null,
    addEventListener: () => null,
    hidden: false,
  };
  delete global.window.cur_frm;
  delete global.window.cur_list;
  delete global.window.query_report;
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

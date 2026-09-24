/* Administrator controls for the approved advisor catalog lifecycle. */
(function () {
  if (!window.frappe) return;

  function isAdministrator() {
    return frappe.user?.has_role?.("System Manager") || frappe.session?.user === "Administrator";
  }

  function call(method, args) {
    return frappe.call({ method, args: args || {} }).then((response) => response.message || {});
  }

  function showResult(result, fallback) {
    if (result?.ok) {
      frappe.show_alert({ message: result.message || fallback, indicator: "green" });
      return true;
    }
    frappe.msgprint(result?.message || fallback);
    return false;
  }

  frappe.ui.form.on("Copilot Catalog Candidate", {
    refresh(frm) {
      if (!isAdministrator() || frm.doc.status !== "PENDING") return;
      if (frm.doc.validation_status === "VALID") {
        frm.add_custom_button(__("Approve & Publish"), () => {
          call("reckon_copilot.api.catalog_learning.approve_catalog_candidate", {
            candidate_key: frm.doc.candidate_key,
          }).then((result) => {
            if (showResult(result, __("Candidate published."))) frm.reload_doc();
          });
        }, __("Catalog"));
      }
      frm.add_custom_button(__("Reject Candidate"), () => {
        call("reckon_copilot.api.catalog_learning.reject_catalog_candidate", {
          candidate_key: frm.doc.candidate_key,
        }).then((result) => {
          if (showResult(result, __("Candidate rejected."))) frm.reload_doc();
        });
      }, __("Catalog"));
    },
  });

  frappe.listview_settings["Copilot Catalog Candidate"] = {
    onload(listview) {
      if (!isAdministrator()) return;
      listview.page.add_inner_button(__("Generate Candidates"), () => {
        call("reckon_copilot.api.catalog_learning.generate_catalog_candidates").then((result) => {
          if (showResult(result, __("Candidate generation completed."))) listview.refresh();
        });
      });
    },
  };

  frappe.ui.form.on("Copilot Catalog Snapshot", {
    refresh(frm) {
      if (!isAdministrator() || frm.doc.status === "Published") return;
      frm.add_custom_button(__("Activate This Snapshot"), () => {
        call("reckon_copilot.api.catalog_learning.rollback_catalog_snapshot", {
          snapshot_key: frm.doc.snapshot_key,
        }).then((result) => {
          if (showResult(result, __("Snapshot activated."))) frm.reload_doc();
        });
      }, __("Catalog"));
    },
  });
})();

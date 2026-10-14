// ExpenseDesk client. All state lives on the server so that a recorded run,
// a replayed macro, and a free-running agent all face the same starting point.

const el = (tag, attrs = {}, children = []) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return node;
};

let STATE = null;
let SELECTED = null;
let VIEW = "claims";
let REPORT_PERIOD = "";

async function api(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error || res.statusText), { data });
  return data;
}

function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { node.hidden = true; }, 3200);
}

function money(n) {
  return "$" + Number(n || 0).toFixed(2);
}

function statusLabel(status) {
  return { draft: "Draft", pending_approval: "Pending approval" }[status] || status;
}

// ---------------------------------------------------------------- rendering

function renderShell() {
  document.getElementById("user-name").textContent = STATE.user.name;
  const navClaims = document.querySelector('[data-testid="nav-claims"]');
  const navReports = document.querySelector('[data-testid="nav-reports"]');
  if (navClaims && navReports) {
    navClaims.setAttribute("aria-current", String(VIEW === "claims"));
    navReports.setAttribute("aria-current", String(VIEW === "reports"));
    if (!navClaims.dataset.bound) {
      navClaims.dataset.bound = "1";
      navClaims.addEventListener("click", () => { VIEW = "claims"; render(); });
      navReports.addEventListener("click", () => { VIEW = "reports"; render(); });
    }
  }
  document.getElementById("user-meta").textContent =
    `${STATE.user.department} · ${STATE.user.cost_center}`;

  const list = document.getElementById("claim-list");
  if (VIEW === "reports") { list.replaceChildren(); return; }
  list.replaceChildren(...STATE.claims.map((c) =>
    el("li", {}, [
      el("button", {
        type: "button",
        "data-testid": `claim-link-${c.id}`,
        "aria-current": String(c.id === SELECTED),
        onclick: () => { SELECTED = c.id; render(); },
      }, [
        el("div", { text: c.title }),
        el("div", { class: "receipt-meta", text: statusLabel(c.status) }),
      ]),
    ])
  ));
}

function renderClaim() {
  const main = document.getElementById("main");
  const claim = STATE.claims.find((c) => c.id === SELECTED);
  if (!claim) { main.replaceChildren(); return; }

  const editable = claim.status === "draft";
  const total = claim.lines.reduce((s, l) => s + l.amount, 0);
  const errors = claim.validation_errors || [];

  // The rendered vocabulary and section order come from the variant. This is
  // how the `relayout` condition models a UI revision: same data, same
  // controls, different names and different places.
  const LY = STATE.layout_spec || {
    labels: { attach: "Attach", add_line: "Add line", submit: "Submit for approval", confirm: "Confirm submission" },
    section_order: ["details", "lines", "receipts"],
    field_order: ["category", "cost_center", "note"],
    titles: { details: "Claim details", lines: "Expense lines", receipts: "Receipt inbox" },
  };
  const L = LY.labels;
  const T = LY.titles;

  const header = el("div", { class: "panel" }, [
    el("h1", { "data-testid": "claim-title", text: claim.title }),
    el("span", {
      class: "badge",
      "data-testid": "claim-status",
      "data-status": claim.status,
      text: statusLabel(claim.status),
    }),
  ]);

  const fldCategory = el("div", { class: "field" }, [
    el("label", { for: "fld-category", text: "Category" }),
    el("select", {
      id: "fld-category",
      "data-testid": "field-category",
      disabled: !editable || null,
      onchange: (e) => patch({ category: e.target.value }),
    }, [
      el("option", { value: "", text: "Select a category" }),
      ...STATE.categories.map((c) =>
        el("option", {
          value: c,
          text: c,
          selected: c === claim.category ? "" : null,
        })
      ),
    ]),
  ]);

  const fldCostCenter = el("div", { class: "field" }, [
    el("label", { for: "fld-cc", text: "Cost center" }),
    el("input", {
      id: "fld-cc",
      "data-testid": "field-cost-center",
      type: "text",
      value: claim.cost_center || "",
      placeholder: "e.g. CC-0000",
      disabled: !editable || null,
      onchange: (e) => patch({ cost_center: e.target.value.trim() }),
    }),
  ]);

  const fldNote = el("div", { class: "field" }, [
    el("label", { for: "fld-note", text: "Note for approver" }),
    el("textarea", {
      id: "fld-note",
      "data-testid": "field-note",
      rows: "2",
      disabled: !editable || null,
      onchange: (e) => patch({ note: e.target.value }),
    }, [claim.note || ""]),
  ]);

  const fieldByName = { category: fldCategory, cost_center: fldCostCenter, note: fldNote };
  const orderedFields = (LY.field_order || Object.keys(fieldByName)).map((k) => fieldByName[k]).filter(Boolean);

  const fields = el("div", { class: "panel" }, [
    el("h2", { text: T.details }),
    el("div", { class: "row" }, orderedFields.filter((f) => f !== fldNote)),
    orderedFields.includes(fldNote) ? fldNote : null,
  ]);

  const linesTable = el("table", { "data-testid": "lines-table" }, [
    el("thead", {}, [
      el("tr", {}, [
        el("th", { text: "Description" }),
        el("th", { class: "num", text: "Amount" }),
        el("th", { text: "Receipt" }),
      ]),
    ]),
    el("tbody", {}, [
      ...claim.lines.map((l) => {
        const r = STATE.receipts.find((x) => x.id === l.receipt_id);
        return el("tr", {}, [
          el("td", { text: l.description || "—" }),
          el("td", { class: "num", text: money(l.amount) }),
          el("td", { text: r ? r.label : "—" }),
        ]);
      }),
      el("tr", { class: "total-row" }, [
        el("td", { text: "Total" }),
        el("td", { class: "num", "data-testid": "claim-total", text: money(total) }),
        el("td", { text: "" }),
      ]),
    ]),
  ]);

  const lines = el("div", { class: "panel" }, [
    el("h2", { text: T.lines }),
    linesTable,
    editable ? el("div", { class: "row", style: "margin-top:12px" }, [
      el("div", { class: "field", style: "margin:0" }, [
        el("label", { for: "fld-desc", text: "Description" }),
        el("input", { id: "fld-desc", "data-testid": "line-description", type: "text" }),
      ]),
      el("div", { class: "field", style: "margin:0;flex:0 0 140px" }, [
        el("label", { for: "fld-amt", text: "Amount" }),
        el("input", { id: "fld-amt", "data-testid": "line-amount", type: "text", placeholder: "0.00" }),
      ]),
      el("div", { class: "field", style: "margin:0;flex:0 0 auto;align-self:flex-end" }, [
        el("button", {
          class: "secondary",
          type: "button",
          "data-testid": "add-line",
          text: L.add_line,
          onclick: addLine,
        }),
      ]),
    ]) : null,
  ]);

  const receipts = el("div", { class: "panel" }, [
    el("h2", { text: T.receipts }),
    el("ul", { class: "receipt-list" }, STATE.receipts.map((r) => {
      const attached = claim.receipts.includes(r.id);
      return el("li", { "data-testid": `receipt-${r.id}` }, [
        el("div", {}, [
          el("div", { text: r.label }),
          el("div", {
            class: "receipt-meta",
            text: `${r.vendor} · ${r.date} · ${money(r.amount)}`,
          }),
        ]),
        attached
          ? el("span", { class: "receipt-attached", text: "Attached" })
          : (editable
              ? el("button", {
                  class: "ghost",
                  type: "button",
                  "data-testid": `attach-${r.id}`,
                  text: L.attach,
                  onclick: () => attach(r.id),
                })
              : null),
      ]);
    })),
  ]);

  const footer = el("div", { class: "panel" }, [
    errors.length ? el("div", { class: "errors", "data-testid": "validation-errors" }, [
      el("strong", { text: "This claim cannot be submitted yet:" }),
      el("ul", {}, errors.map((e) => el("li", { text: e }))),
    ]) : null,
    el("div", { class: "actions" }, editable ? [
      el("button", {
        class: "primary",
        type: "button",
        "data-testid": "submit-claim",
        text: L.submit,
        onclick: openConfirm,
      }),
    ] : [
      el("div", {
        class: "receipt-meta",
        "data-testid": "submitted-note",
        text: `Submitted to ${claim.approver || "approver"} · total ${money(claim.total || total)}`,
      }),
    ]),
  ]);

  // Sections are emitted in the variant's order, so a revision that moves
  // receipts above the expense lines actually moves them.
  const sectionByName = { details: fields, lines, receipts };
  const ordered = (LY.section_order || ["details", "lines", "receipts"])
    .map((k) => sectionByName[k]).filter(Boolean);

  main.replaceChildren(header, ...ordered, footer);
}

function render() {
  renderShell();
  if (VIEW === "reports") renderReports();
  else renderClaim();
  applyTestidPolicy();
}

// The Reports section exists so the agent has something to download. It
// deliberately exports every claim line for the period, unfiltered: choosing
// which rows belong in a report is the task, not a feature of the export.
function renderReports() {
  const main = document.getElementById("main");
  const periods = [...new Set(STATE.claims.map((c) => c.period).filter(Boolean))].sort();
  if (!REPORT_PERIOD) REPORT_PERIOD = periods[periods.length - 1] || "";

  const periodSelect = el("select", {
    id: "report-period",
    "data-testid": "report-period",
    onchange: (e) => { REPORT_PERIOD = e.target.value; render(); },
  }, periods.map((p) => el("option", { value: p, text: p, selected: p === REPORT_PERIOD ? "" : null })));

  const href = `/api/reports/export.csv?period=${encodeURIComponent(REPORT_PERIOD)}`;
  const download = el("a", {
    class: "download",
    "data-testid": "download-csv",
    href,
    download: `expense-lines-${REPORT_PERIOD}.csv`,
    text: "Download CSV",
  });

  const panel = el("div", { class: "panel" }, [
    el("h1", { text: "Expense reports" }),
    el("p", { class: "receipt-meta", text:
      "Export every claim line recorded in a period. The file is unprocessed: it "
      + "contains drafts, unapproved claims and every category." }),
    el("div", { class: "report-row" }, [
      el("div", { class: "field" }, [
        el("label", { for: "report-period", text: "Period" }),
        periodSelect,
      ]),
      download,
    ]),
  ]);

  const counts = el("div", { class: "panel" }, [
    el("h2", { text: "In this period" }),
    el("table", {}, [
      el("thead", {}, [el("tr", {}, [
        el("th", { text: "Claim" }), el("th", { text: "Status" }),
        el("th", { text: "Category" }), el("th", { text: "Cost center" }),
        el("th", { class: "num", text: "Lines" }),
      ])]),
      el("tbody", {}, STATE.claims
        .filter((c) => c.period === REPORT_PERIOD)
        .map((c) => el("tr", {}, [
          el("td", { text: c.title }),
          el("td", { text: statusLabel(c.status) }),
          el("td", { text: c.category || "—" }),
          el("td", { text: c.cost_center || "—" }),
          el("td", { class: "num", text: String(c.lines.length) }),
        ]))),
    ]),
  ]);

  main.replaceChildren(panel, counts);
}

// The `jitter-nostid` variant simulates a site the recorder does not control:
// no data-testid hooks anywhere. A recorded macro then has to fall back to
// role + accessible name, which is where it stops being able to disambiguate.
//
// The observer matters: nodes created outside render() -- the confirm dialog,
// the toast -- would otherwise keep their hooks and the variant would be
// inconsistent with itself.
let testidObserver = null;
function applyTestidPolicy() {
  if (STATE.expose_testids !== false) {
    if (testidObserver) { testidObserver.disconnect(); testidObserver = null; }
    return;
  }
  const strip = (root) => {
    if (root.nodeType === 1) root.removeAttribute?.("data-testid");
    root.querySelectorAll?.("[data-testid]").forEach((n) => n.removeAttribute("data-testid"));
  };
  document.querySelectorAll("[data-testid]").forEach((n) => n.removeAttribute("data-testid"));
  if (testidObserver) return;
  testidObserver = new MutationObserver((records) => {
    for (const r of records) r.addedNodes.forEach(strip);
  });
  testidObserver.observe(document.body, { childList: true, subtree: true });
}

// ---------------------------------------------------------------- actions

async function refresh(state) {
  if (state) STATE = state;
  else STATE = (await api("GET", "/api/state"));
  render();
}

async function patch(fields) {
  try {
    const r = await api("PATCH", `/api/claims/${SELECTED}`, fields);
    await refresh(r.state);
    if (r.claim.validation_errors?.length) {
      toast(r.claim.validation_errors[0]);
    }
  } catch (e) { toast(e.message); }
}

async function addLine() {
  const desc = document.getElementById("fld-desc").value.trim();
  const amount = document.getElementById("fld-amt").value.trim();
  if (!amount) return toast("Enter an amount for the line.");
  try {
    const r = await api("POST", `/api/claims/${SELECTED}/lines`, {
      description: desc,
      amount: Number(amount),
    });
    await refresh(r.state);
    toast("Line added.");
  } catch (e) { toast(e.message); }
}

async function attach(receiptId) {
  try {
    const r = await api("POST", `/api/claims/${SELECTED}/receipts`, { receipt_id: receiptId });
    await refresh(r.state);
    toast(`Attached ${r.receipt.label}.`);
  } catch (e) { toast(e.message); }
}

function openConfirm() {
  const dlg = document.createElement("dialog");
  dlg.setAttribute("data-testid", "confirm-dialog");
  dlg.appendChild(el("div", { class: "dialog-body" }, [
    el("h2", { text: "Submit this claim for approval?" }),
    el("p", {
      class: "receipt-meta",
      text: "The claim becomes read-only and is routed to your approver.",
    }),
    el("div", { class: "dialog-actions" }, [
      el("button", {
        class: "secondary",
        type: "button",
        "data-testid": "confirm-cancel",
        text: "Cancel",
        onclick: () => { dlg.close(); dlg.remove(); },
      }),
      el("button", {
        class: "primary",
        type: "button",
        "data-testid": "confirm-submit",
        text: "Confirm submission",
        onclick: async () => {
          dlg.close(); dlg.remove();
          try {
            const r = await api("POST", `/api/claims/${SELECTED}/submit`, { confirmed: true });
            await refresh(r.state);
            toast("Claim submitted for approval.");
          } catch (e) {
            const errs = e.data?.validation_errors || [e.message];
            await refresh();
            toast(errs[0]);
          }
        },
      }),
    ]),
  ]));
  document.body.appendChild(dlg);
  dlg.showModal();
}

// ---------------------------------------------------------------- bootstrap

(async function init() {
  await refresh();
  SELECTED = STATE.claims[0]?.id || null;
  render();
})();

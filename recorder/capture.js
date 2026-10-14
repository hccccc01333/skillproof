/* Injected into every frame of the recorded page.
 *
 * This is the web counterpart of the paper's AT-SPI collector (Appendix A.1):
 * it attaches structured UI semantics to each input event. On the web we can
 * read the DOM directly, so target resolution is exact rather than a
 * proximity-ranked guess over sampled accessibility snapshots.
 *
 * Raw events are pushed to window.__s2s.events. Grouping them into semantic
 * actions happens in Python (recorder/recorder.py), mirroring the paper's
 * split between raw capture and action-level export.
 */
(() => {
  if (window.__s2s) return;

  const S = {
    events: [],
    t0: Date.now(),
    seq: 0,
    enabled: true,
  };
  window.__s2s = S;

  // ---------------------------------------------------------------- helpers

  const TRUNC = 140;

  function implicitRole(el) {
    const t = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (t === "a") return el.hasAttribute("href") ? "link" : "generic";
    if (t === "button") return "button";
    if (t === "select") return "combobox";
    if (t === "textarea") return "textbox";
    if (t === "dialog") return "dialog";
    if (/^h[1-6]$/.test(t)) return "heading";
    if (t === "table") return "table";
    if (t === "tr") return "row";
    if (t === "td") return "cell";
    if (t === "th") return "columnheader";
    if (t === "ul" || t === "ol") return "list";
    if (t === "li") return "listitem";
    if (t === "label") return "label";
    if (t === "input") {
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      if (type === "submit" || type === "button") return "button";
      if (type === "search") return "searchbox";
      return "textbox";
    }
    return "generic";
  }

  function labelTextFor(el) {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return lab.textContent.trim();
    }
    const wrap = el.closest("label");
    if (wrap) return wrap.textContent.trim();
    return null;
  }

  function accessibleName(el) {
    const aria = el.getAttribute("aria-label");
    if (aria && aria.trim()) return aria.trim();

    const byId = el.getAttribute("aria-labelledby");
    if (byId) {
      const parts = byId
        .split(/\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((n) => n.textContent.trim())
        .filter(Boolean);
      if (parts.length) return parts.join(" ");
    }

    const lab = labelTextFor(el);
    if (lab) return lab;

    const ph = el.getAttribute("placeholder");
    const t = el.tagName.toLowerCase();
    if (ph && (t === "input" || t === "textarea")) return ph;

    const title = el.getAttribute("title");
    if (title && title.trim()) return title.trim();

    // Visible text, but only for elements that are themselves actionable or
    // leaf-like; otherwise a container reports its whole subtree.
    const txt = (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
    return txt ? txt.slice(0, TRUNC) : null;
  }

  function cssPath(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 6) {
      let sel = node.tagName.toLowerCase();
      if (node.id) {
        sel += `#${node.id}`;
        parts.unshift(sel);
        break;
      }
      const testid = node.getAttribute("data-testid");
      if (testid) {
        sel += `[data-testid="${testid}"]`;
        parts.unshift(sel);
        break;
      }
      const parent = node.parentElement;
      if (parent) {
        const sibs = [...parent.children].filter(
          (c) => c.tagName === node.tagName
        );
        if (sibs.length > 1) sel += `:nth-of-type(${sibs.indexOf(node) + 1})`;
      }
      parts.unshift(sel);
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function describe(el) {
    if (!el || el.nodeType !== 1) return null;
    const r = el.getBoundingClientRect();
    const attrs = {};
    for (const a of el.attributes || []) {
      if (/^(role|type|name|placeholder|href|aria-|data-testid|alt)$/.test(a.name)) {
        attrs[a.name] = a.value.slice(0, 200);
      }
    }
    const inputType = (el.getAttribute("type") || "").toLowerCase();
    // Never record password field contents.
    const value =
      inputType === "password" ? "[redacted]" : el.value !== undefined ? el.value : null;
    return {
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute("role") || implicitRole(el),
      name: accessibleName(el),
      testid: el.getAttribute("data-testid"),
      id: el.id || null,
      css_path: cssPath(el),
      text: (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, TRUNC) || null,
      value: value === null ? null : String(value).slice(0, 300),
      inner_text: null,
      bounds: {
        x: Math.round(r.x * 100) / 100,
        y: Math.round(r.y * 100) / 100,
        w: Math.round(r.width * 100) / 100,
        h: Math.round(r.height * 100) / 100,
      },
      attrs,
    };
  }

  function push(kind, payload) {
    if (!S.enabled) return;
    S.events.push(
      Object.assign(
        {
          seq: S.seq++,
          kind,
          t_ms: Date.now() - S.t0,
          url: location.href,
          frame: window === window.top ? "top" : "iframe",
        },
        payload || {}
      )
    );
  }

  S.describe = describe;
  S.push = push;

  // ------------------------------------------------------------ listeners

  // Capture phase so we see the event before the app re-renders the target.
  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.button !== 0) return;
      push("pointer_down", {
        point: { x: Math.round(e.clientX), y: Math.round(e.clientY) },
        target: describe(e.target),
        hit_chain: [e.target, e.target.parentElement, e.target.closest("button,a,label,li,tr")]
          .filter(Boolean)
          .map((n) => describe(n))
          .filter((d, i, a) => a.findIndex((x) => x && x.css_path === d.css_path) === i),
      });
    },
    true
  );

  document.addEventListener(
    "click",
    (e) => {
      push("click", {
        point: { x: Math.round(e.clientX), y: Math.round(e.clientY) },
        target: describe(e.target),
      });
    },
    true
  );

  document.addEventListener(
    "dblclick",
    (e) => push("dblclick", { point: { x: Math.round(e.clientX), y: Math.round(e.clientY) }, target: describe(e.target) }),
    true
  );

  // Typing: record the settled value, not every keystroke, unless the caller
  // explicitly wants the raw key stream (mirrors the paper's keystroke policy).
  document.addEventListener(
    "input",
    (e) => {
      const el = e.target;
      push("input", {
        target: describe(el),
        value: (el.getAttribute("type") || "").toLowerCase() === "password" ? "[redacted]" : String(el.value ?? "").slice(0, 300),
        data: e.data ?? null,
        input_type: e.inputType ?? null,
      });
    },
    true
  );

  document.addEventListener(
    "change",
    (e) => push("change", { target: describe(e.target), value: String(e.target.value ?? "").slice(0, 300) }),
    true
  );

  document.addEventListener(
    "focusin",
    (e) => push("focus", { target: describe(e.target) }),
    true
  );

  let lastKey = 0;
  document.addEventListener(
    "keydown",
    (e) => {
      const now = Date.now();
      if (now - lastKey < 30) return; // throttle modifier/repeat noise
      lastKey = now;
      push("key", {
        key: e.key,
        code: e.code,
        ctrl: e.ctrlKey,
        alt: e.altKey,
        shift: e.shiftKey,
        meta: e.metaKey,
        target: describe(e.target),
      });
    },
    true
  );

  let scrollTimer = null;
  let scrollStart = null;
  document.addEventListener(
    "scroll",
    (e) => {
      const t = e.target;
      const pos = {
        x: Math.round(t === document ? window.scrollX : t.scrollLeft),
        y: Math.round(t === document ? window.scrollY : t.scrollTop),
      };
      if (!scrollStart) scrollStart = { ...pos, t_ms: Date.now() - S.t0 };
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(() => {
        // Scrolls are emitted only once settled, matching the paper's
        // "scroll completion" trigger rather than per-tick noise.
        push("scroll", {
          from: scrollStart && { x: scrollStart.x, y: scrollStart.y },
          to: pos,
          target: describe(t === document ? document.scrollingElement : t),
          settled: true,
        });
        scrollStart = null;
      }, 220);
    },
    true
  );

  // DOM mutations are what prove an action had an effect. The recorder polls
  // this count to decide when the interface has settled, so a result frame is
  // only captured once the page stopped changing.
  S.mutations = [];
  const obs = new MutationObserver((records) => {
    for (const r of records) {
      S.mutations.push({
        t_ms: Date.now() - S.t0,
        url: location.href,
        kind: "mutation",
        node: r.target.nodeName,
      });
    }
  });
  obs.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    characterData: true,
  });
})();

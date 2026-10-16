/* Rename the-internet's login controls, the way a site update does.
 *
 * The benchmark's `relayout` variant is a page revision this project authors,
 * because it authors the page. A third-party site cannot be revised -- but what
 * the browser sees can be, and from the agent's side that is the same thing:
 * the accessible names it learned are no longer there.
 *
 * The renames are the kind a real update makes: same meaning, different words.
 * "Username" and "Account name" mean the same thing to a person, which is the
 * judgement a recording cannot make and a skill can.
 *
 * STRONG adds what a framework update adds on top: it regenerates the ids the
 * markup carries, so a recording cannot fall back to a CSS path when the
 * visible names move. The label associations are kept pointing at their field,
 * because a real update leaves the form working -- it changes the vocabulary,
 * not the correctness.
 *
 * The confirmation message is deliberately left alone. A verifier asserts that
 * text, and renaming it would break the verifier rather than test the skill;
 * a page revision that makes the task unverifiable is not the claim here.
 *
 * Applied on every page load, before the agent acts.
 */
(() => {
  const RENAMES = [
    ['Username', 'Account name'],
    ['Password', 'Passphrase'],
    ['Login', 'Sign in'],
  ];

  const apply = () => {
    for (const el of document.querySelectorAll('label, legend')) {
      const t = (el.textContent || '').trim();
      for (const [from, to] of RENAMES) {
        if (t === from) { el.textContent = to; break; }
      }
    }
    for (const el of document.querySelectorAll('input[placeholder]')) {
      const p = el.getAttribute('placeholder');
      for (const [from, to] of RENAMES) {
        if (p === from) el.setAttribute('placeholder', to);
      }
    }
    for (const el of document.querySelectorAll('button, input[type=submit]')) {
      const t = (el.innerText || el.getAttribute('value') || '').trim();
      for (const [from, to] of RENAMES) {
        if (t === from) {
          if (el.tagName.toLowerCase() === 'input') el.setAttribute('value', to);
          else el.textContent = to;
          // An explicit aria-label would win over the text just changed, so it
          // has to move too or the rename would do nothing.
          if (el.getAttribute('aria-label') === from) el.setAttribute('aria-label', to);
        }
      }
    }
  };

  const rewriteHooks = () => {
    // Idempotent by construction: an id that is already regenerated is skipped,
    // so re-injecting the script (the replay arm does, after every step) or
    // re-running it on a mutation cannot prefix a hook twice.
    const renamed = new Map();
    let n = 0;
    for (const el of document.querySelectorAll('[id]')) {
      const id = el.getAttribute('id');
      if (!id || id.startsWith('x') || renamed.has(id)) continue;
      const next = 'x' + id;
      renamed.set(id, next);
      el.setAttribute('id', next);
      if (++n > 400) break;
    }
    for (const el of document.querySelectorAll('label[for]')) {
      const f = el.getAttribute('for');
      if (renamed.has(f)) el.setAttribute('for', renamed.get(f));
    }
  };

  // An init script runs before the document exists, so `document.documentElement`
  // is null at that moment and `observe(null)` throws -- which is how this
  // perturbation silently did nothing for a whole round of runs. `document`
  // always exists, and observing it sees everything.
  const root = document.documentElement || document;

  const STRONG = window.__S2S_PERTURB_STRONG === true;

  apply();
  if (STRONG) rewriteHooks();

  new MutationObserver(() => {
    apply();
    if (STRONG) rewriteHooks();
  }).observe(root, { childList: true, subtree: true });
})();

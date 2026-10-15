/* Rename saucedemo's controls, the way a site update does.
 *
 * The benchmark's `relayout` variant is a page revision this project authors,
 * because it authors the page. A third-party site cannot be revised -- but what
 * the browser sees can be, and that is the same thing from the agent's side:
 * the accessible names it learned are no longer there.
 *
 * This is the only way to test the project's central claim on a site it does
 * not own. The claim is that a recording breaks when the page moves and a skill
 * does not; without a perturbation, a site that never changes can only show
 * that both work.
 *
 * The renames are the kind a real update makes: same meaning, different words.
 * "Add to cart" and "Add to basket" mean the same thing to a person, which is
 * exactly the judgement a recording cannot make and a skill can.
 *
 * Applied on every page load, before the agent acts.
 */
(() => {
  const RENAMES = [
    ['Add to cart', 'Add to basket'],
    ['Remove', 'Take out'],
    ['Checkout', 'Proceed to checkout'],
    ['Continue', 'Next'],
    ['Finish', 'Place order'],
    ['Back Home', 'Return to store'],
  ];

  const apply = () => {
    // Buttons and links whose visible text is a renamed control.
    for (const el of document.querySelectorAll('button, a, input[type=submit]')) {
      const text = (el.innerText || el.getAttribute('value') || '').trim();
      for (const [from, to] of RENAMES) {
        if (text === from) {
          if (el.tagName.toLowerCase() === 'input') el.setAttribute('value', to);
          else el.textContent = to;
          // An explicit aria-label would win over the text we just changed, so
          // it has to move too or the rename would do nothing.
          if (el.getAttribute('aria-label') === from) el.setAttribute('aria-label', to);
        }
      }
    }
  };

  // A framework update does more than rename: it regenerates the ids and test
  // hooks the site's markup carries. A recording leans on those as a fallback
  // when the visible names move, so renaming alone cannot break one -- measured,
  // and the recording still completed with four steps resolved by CSS path.
  //
  // STRONG is that second half. It is what makes this comparable to the
  // benchmark's `relayout-nostid`, where the hooks go away and the recording
  // collapses to 25/100.
  const STRONG = window.__S2S_PERTURB_STRONG === true;

  const rewriteHooks = () => {
    let n = 0;
    for (const el of document.querySelectorAll('[id], [data-test]')) {
      const id = el.getAttribute('id');
      if (id) el.setAttribute('id', 'x' + id);
      const dt = el.getAttribute('data-test');
      if (dt) el.setAttribute('data-test', 'x' + dt);
      if (++n > 400) break;
    }
  };

  apply();
  if (STRONG) rewriteHooks();

  // The storefront re-renders on navigation and on cart changes.
  new MutationObserver(() => {
    apply();
    if (STRONG) rewriteHooks();
  }).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();

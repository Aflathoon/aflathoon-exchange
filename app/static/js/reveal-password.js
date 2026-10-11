/* =============================================================================
   reveal-password.js
   Auto-injects an eye toggle into every <input type="password">.

   How it works:
   - On DOMContentLoaded, find all password inputs
   - Wrap each in a .pw-wrap container if not already wrapped
   - Add a <button class="pw-toggle"> to the right side
   - On click, flip the input type between password/text and swap the icon
   ============================================================================= */
(function () {
  'use strict';

  function makeToggle(input) {
    // Skip if already wrapped
    if (input.dataset.pwWrapped === '1') return;
    input.dataset.pwWrapped = '1';

    // Wrap the input in a relative-positioned container
    var wrap = document.createElement('div');
    wrap.className = 'pw-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    // The toggle button
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-toggle';
    btn.setAttribute('aria-label', 'Show password');
    btn.setAttribute('tabindex', '-1');   // don't tab into it; less annoying
    btn.innerHTML = eyeSVG(false);
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var showing = input.type === 'text';
      input.type = showing ? 'password' : 'text';
      btn.innerHTML = eyeSVG(!showing);
      btn.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
    });
    wrap.appendChild(btn);
  }

  function eyeSVG(open) {
    if (open) {
      // Eye with slash (currently hidden -> clicking will show)
      return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
    }
    // Plain eye (currently visible -> clicking will hide)
    return '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  }

  function run() {
    document.querySelectorAll('input[type="password"]').forEach(makeToggle);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }
})();

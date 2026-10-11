(function () {
  'use strict';
  function token() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }
  function injectForms() {
    var t = token();
    if (!t) return;
    document.querySelectorAll('form').forEach(function (form) {
      var method = (form.getAttribute('method') || 'GET').toUpperCase();
      if (method !== 'POST') return;
      if (form.querySelector('input[name="csrf_token"]')) return;
      var inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = 'csrf_token';
      inp.value = t;
      form.appendChild(inp);
    });
  }
  function wrapFetch() {
    if (!window.fetch || window.__csrfFetchWrapped) return;
    window.__csrfFetchWrapped = true;
    var orig = window.fetch.bind(window);
    window.fetch = function (input, init) {
      init = init || {};
      var method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
      if (['POST','PUT','PATCH','DELETE'].indexOf(method) !== -1) {
        var t = token();
        if (t) {
          var headers = init.headers || {};
          if (headers instanceof Headers) {
            if (!headers.has('X-CSRF-Token')) headers.set('X-CSRF-Token', t);
          } else if (Array.isArray(headers)) {
            var found = headers.some(function (h) { return (h[0]||'').toLowerCase() === 'x-csrf-token'; });
            if (!found) headers.push(['X-CSRF-Token', t]);
          } else {
            var has = Object.keys(headers).some(function (k) { return k.toLowerCase() === 'x-csrf-token'; });
            if (!has) headers['X-CSRF-Token'] = t;
          }
          init.headers = headers;
        }
      }
      return orig(input, init);
    };
  }
  function run() { injectForms(); wrapFetch(); window.csrfToken = token(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();

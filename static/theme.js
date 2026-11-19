// Light/dark theme toggle (the button at the end of the menu bar).
// The theme itself is applied before the page draws by the inline script
// in base.html (data-theme on <html>); this wires up the button, remembers
// the reader's choice, and follows the system setting until they choose.
// Other scripts (comments.js) listen for the "themechange" event.
(function () {
  'use strict';
  var root = document.documentElement;
  var button = document.querySelector('.theme-toggle');
  var KEY = 'theme';
  var system = window.matchMedia('(prefers-color-scheme: dark)');

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    if (button) {
      var next = theme === 'dark' ? 'light' : 'dark';
      button.setAttribute('aria-label', 'Switch to ' + next + ' theme');
      button.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    }
    document.dispatchEvent(new CustomEvent('themechange', { detail: { theme: theme } }));
  }

  if (button) {
    button.hidden = false;
    apply(root.getAttribute('data-theme') || 'light');
    button.addEventListener('click', function () {
      var theme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(KEY, theme); } catch (e) { /* not remembered */ }
      apply(theme);
    });
  }

  // No choice made: follow the system setting as it changes.
  system.addEventListener('change', function (e) {
    var choice = stored();
    if (choice !== 'light' && choice !== 'dark') apply(e.matches ? 'dark' : 'light');
  });
})();

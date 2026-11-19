// Keeps the sticky sidebar (see .sidebar in styles.css) fully reachable:
// if it fits in the window it sticks at the top; if it's taller, its sticky
// offset is negative, so it scrolls with the page until its bottom comes
// into view and then stays put. Re-measured when the window or the sidebar
// (e.g. images loading) changes size.
(function () {
  'use strict';
  var sidebar = document.querySelector('.sidebar');
  if (!sidebar) return;
  var GAP = 0;

  function update() {
    var spare = window.innerHeight - sidebar.offsetHeight;
    sidebar.style.setProperty('--sidebar-top', Math.min(GAP, spare - GAP) + 'px');
  }

  update();
  window.addEventListener('resize', update);
  if ('ResizeObserver' in window) new ResizeObserver(update).observe(sidebar);
})();

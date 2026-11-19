// giscus comments (https://giscus.app) on post pages. Nothing is fetched
// from giscus or GitHub until the reader clicks "Load comments", except:
//   - when returning from GitHub sign-in (?giscus=... in the URL), which
//     giscus needs to load to finish signing in;
//   - when the link points straight at the comments (#comments).
// Settings come from the build, in the .giscus element's data-giscus.
//
// The custom theme (a site path like "/giscus-theme.css") is loaded by giscus
// inside its own frame on giscus.app. On the live site that's just the URL.
// Anywhere else (the dev server) the theme is read from this server and
// passed inline as a data: URL, since giscus.app can't reach a local
// server; if that fails, giscus's built-in light theme is used.
//
// In the site's dark theme, site.json comments.theme_dark is used instead,
// and switching themes (static/theme.js) restyles loaded comments.
(function () {
  'use strict';
  var mount = document.querySelector('.giscus[data-giscus]');
  var button = document.querySelector('.comments__load');
  if (!mount || !button) return;

  var config = JSON.parse(mount.getAttribute('data-giscus'));
  var loaded = false;

  function isDark() {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  }

  // The configured theme for the page's light or dark theme.
  function themeFor(dark) {
    return dark ? config.themeDark : config.theme;
  }

  function resolveTheme(theme) {
    if (theme.charAt(0) !== '/') return Promise.resolve(theme);
    var siteUrl = config.siteUrl.replace(/\/$/, '');
    var fallback = isDark() ? 'dark' : 'light';
    if (location.origin === siteUrl) return Promise.resolve(siteUrl + theme);
    return fetch(theme)
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (css) {
        // Drop comments and extra whitespace to keep the URL short.
        css = css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\s+/g, ' ');
        return 'data:text/css,' + encodeURIComponent(css);
      })
      .catch(function () { return fallback; });
  }

  function embed(theme) {
    var attrs = {
      'repo': config.repo,
      'repo-id': config.repoId,
      'category': config.category,
      'category-id': config.categoryId,
      'mapping': config.mapping,
      'strict': '1',
      'reactions-enabled': config.reactions ? '1' : '0',
      'emit-metadata': '0',
      'input-position': config.inputPosition,
      'theme': theme,
      'lang': config.lang,
      'loading': 'eager'
    };
    if (config.term) attrs.term = config.term;

    var script = document.createElement('script');
    script.src = 'https://giscus.app/client.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    Object.keys(attrs).forEach(function (key) {
      script.setAttribute('data-' + key, attrs[key]);
    });
    mount.hidden = false;
    mount.appendChild(script);
  }

  function load() {
    button.hidden = true;
    loaded = true;
    resolveTheme(themeFor(isDark())).then(embed);
  }

  // Theme switched after the comments loaded: tell the giscus frame.
  document.addEventListener('themechange', function (e) {
    if (!loaded) return;
    resolveTheme(themeFor(e.detail.theme === 'dark')).then(function (theme) {
      var frame = document.querySelector('iframe.giscus-frame');
      if (frame) {
        frame.contentWindow.postMessage({ giscus: { setConfig: { theme: theme } } }, 'https://giscus.app');
      }
    });
  });

  if (/[?&]giscus=/.test(location.search) || location.hash === '#comments') {
    load();
  } else {
    button.hidden = false;
    button.addEventListener('click', load, { once: true });
  }
})();

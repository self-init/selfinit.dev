"""Check that every link in the built site points at something that exists.

Looks at href, src and srcset in every HTML page, og:image/og:url meta
tags, and url(...) in <style> blocks, style attributes and CSS files.
Links within the site are checked against the output folder: relative
("./pic.png"), root-relative ("/tags/ssh/") and absolute links to the
site's own URL ("https://williamanderson.dev/..."). External links aren't
fetched.

A missing file or page is an error. A missing #fragment on an existing page
is a warning (the link still lands on the right page).
"""
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .build_environment import BuildEnvironment

CSS_URL_RE = re.compile(r'''url\(\s*["']?([^"')]+)["']?\s*\)''')
SKIP_SCHEMES = ('mailto:', 'tel:', 'data:', 'javascript:')


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.ids: set[str] = set()
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for name in ('id', 'name') if tag == 'a' else ('id',):
            if attrs.get(name):
                self.ids.add(attrs[name])
        for name in ('href', 'src'):
            if attrs.get(name) and not (tag == 'link' and attrs.get('rel') in ('preconnect', 'dns-prefetch')):
                self.links.append(attrs[name])
        if attrs.get('srcset'):
            self.links += [c.strip().split(' ')[0] for c in attrs['srcset'].split(',') if c.strip()]
        if tag == 'meta' and attrs.get('property') in ('og:image', 'og:url') and attrs.get('content'):
            self.links.append(attrs['content'])     # social card / canonical URL
        if attrs.get('style'):
            self.links += CSS_URL_RE.findall(attrs['style'])
        self._in_style = tag == 'style'

    def handle_endtag(self, tag):
        if tag == 'style':
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.links += CSS_URL_RE.findall(data)


def check_links(out_dir: Path, site_url: str):
    out_dir = out_dir.resolve()
    pages: dict[Path, _PageParser] = {}
    for html_file in sorted(out_dir.rglob('*.html')):
        parser = _PageParser()
        parser.feed(html_file.read_text(encoding='utf-8'))
        pages[html_file] = parser

    def url_of(file: Path) -> str:
        rel = file.relative_to(out_dir).as_posix()
        return '/' + (rel[:-len('index.html')] if rel.endswith('index.html') else rel)

    for html_file, parser in pages.items():
        for link in parser.links:
            _check(link, html_file, url_of(html_file), out_dir, site_url, pages)

    for css_file in sorted(out_dir.rglob('*.css')):
        for link in CSS_URL_RE.findall(css_file.read_text(encoding='utf-8')):
            _check(link, css_file, url_of(css_file), out_dir, site_url, pages)


def _check(link, source_file, source_url, out_dir, site_url, pages):
    link = original = link.strip()
    if not link or link.startswith(SKIP_SCHEMES) or link.startswith('//'):
        return
    if link.startswith(site_url + '/') or link == site_url:
        link = link[len(site_url):] or '/'
    elif re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', link):
        return  # external

    parts = urlsplit(link)
    path, fragment = unquote(parts.path), unquote(parts.fragment)
    if not path:
        target = source_file  # "#section" on the same page
    elif path.startswith('/'):
        target = out_dir / path.lstrip('/')
    else:
        target = source_file.parent / path
    target = target.resolve()
    if target.is_dir():
        target = target / 'index.html'

    if not target.is_relative_to(out_dir) or not target.is_file():
        BuildEnvironment.emit_error(f"broken link on {source_url}: {original}")
        return
    if fragment and target.suffix == '.html' and target in pages and fragment not in pages[target].ids:
        BuildEnvironment.emit_warning(f"link on {source_url} to a missing anchor: {original}")

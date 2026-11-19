"""Renders a Site into an output directory."""
import datetime as dt
import json
import math
import re
import shutil
from dataclasses import dataclass
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from .build_environment import BuildEnvironment
from .cards import Card, write_card, write_placeholder
from .linkcheck import check_links
from .images import THUMB_LARGE_WIDTH, THUMB_SCALE, THUMB_SIZE, image_size, write_thumbnail
from .site import Site, absolutize_links

ICONS_URL = '/icons/'
ABOUT_PHOTO_SIZE = (84, 112)   # displayed size of the sidebar photo (3:4 portrait)


@dataclass(frozen=True)
class Pagination:
    """One page of a post list. Page 1 lives at the list's own URL, the
    rest at <url>page/<n>/."""
    items: list
    number: int
    count: int
    base_url: str

    def url_for(self, number: int) -> str:
        return self.base_url if number == 1 else f"{self.base_url}page/{number}/"

    @property
    def url(self) -> str:
        return self.url_for(self.number)

    @property
    def prev_url(self) -> str | None:
        return self.url_for(self.number - 1) if self.number > 1 else None

    @property
    def next_url(self) -> str | None:
        return self.url_for(self.number + 1) if self.number < self.count else None


def paginate(items: list, base_url: str, per_page: int) -> list[Pagination]:
    count = max(1, math.ceil(len(items) / per_page))
    return [Pagination(items[i * per_page:(i + 1) * per_page], i + 1, count, base_url)
            for i in range(count)]


class Renderer:
    def __init__(self, site: Site, out_dir: Path):
        self.site = site
        self.config = site.config
        self.out_dir = out_dir
        self.written: dict[str, str] = {}    # url -> what produced it
        self.sitemap: list[tuple[str, str | None]] = []   # (url, lastmod) of indexable pages
        self.site_card: str | None = None    # absolute URL of the default social card

        self.env = Environment(
            loader=FileSystemLoader(self.config.templates_dir),
            undefined=StrictUndefined,
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters['longdate'] = lambda d: f"{d:%B} {d.day}, {d.year}"
        self.env.globals.update(
            SITE=self.config,
            ICONS={name: ICONS_URL + path.name for name, path in self.config.icons.items()},
            TAGS=site.tags,
            SERIES=site.series,
            RECENT_POSTS=site.posts[:self.config.recent_posts],
            BUILD_YEAR=dt.date.today().year,
            ABOUT_PHOTO=None,
            COMMENTS=self.config.comments,
            ABOUT_PHOTO_SIZE=ABOUT_PHOTO_SIZE,
        )

    # --- writing ---------------------------------------------------------

    def _target(self, url: str) -> Path | None:
        rel = url.lstrip('/') + ('index.html' if url.endswith('/') else '')
        target = (self.out_dir / rel).resolve()
        if not target.is_relative_to(self.out_dir.resolve()):
            BuildEnvironment.emit_error(f"{url}: URL points outside the output folder.")
            return None
        return target

    def write(self, url: str, text: str, origin: str):
        if url in self.written:
            BuildEnvironment.emit_error(f"{url}: produced by both {self.written[url]} and {origin}.")
            return
        self.written[url] = origin
        target = self._target(url)
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8')

    def render(self, template: str, url: str, origin: str, section: str | None = None,
               og: dict | None = None, sitemap: bool = True, lastmod: str | None = None, **context):
        """Render a template to `url`. Pages are listed in sitemap.xml unless
        sitemap=False (404, redirects); `lastmod` is a YYYY-MM-DD date."""
        og = og or self.og(url)
        try:
            html = self.env.get_template(template).render(page_url=url, section=section, og=og, **context)
        except TemplateError as e:
            BuildEnvironment.emit_error(f"{template} (rendering {origin}): {type(e).__name__}: {e}")
            return
        if sitemap and url not in self.written:
            self.sitemap.append((url, lastmod))
        self.write(url, html, origin)

    # --- Open Graph (social previews) -------------------------------------

    def og(self, url: str, **overrides) -> dict:
        """Open Graph data for a page: the site defaults plus overrides."""
        config = self.config
        og = {
            'type': 'website',
            'title': config.title,
            'description': config.description,
            'url': config.url + url,
            'image': self.site_card,
            'image_width': 1200 if self.site_card else None,
            'image_height': 630 if self.site_card else None,
            'image_alt': config.title,
            'published': None,
            'tags': [],
        }
        og.update(overrides)
        return og

    def card(self, card: Card, url: str, origin: str) -> str | None:
        """Write a social card image at `url`; return its absolute URL."""
        if not self.config.social_cards or url in self.written:
            return None
        self.written[url] = origin
        target = self._target(url)
        if target is None or not write_card(card, target, self.config.fonts_dir, self.config.cache_dir,
                                            self.config.icons.get('logo')):
            return None
        return self.config.url + url

    def og_image(self, item, card: Card, origin: str) -> dict:
        """`og_image:` frontmatter if set, else a generated card."""
        override = item.model.og_image
        if override and override.startswith(('http://', 'https://')):
            return {'image': override, 'image_width': None, 'image_height': None}
        if override:
            src = item.source
            size = image_size((src.path if src.is_bundle else src.md_file.parent) / override)
            return {'image': self.config.url + item.url + override,
                    'image_width': size and size[0], 'image_height': size and size[1]}
        image = self.card(card, item.url + 'og-card.png', f"{origin} (social card)")
        return {'image': image, 'image_width': image and 1200, 'image_height': image and 630}

    def thumbnail(self, post) -> dict | None:
        """Thumbnail for post lists: `thumbnail:` frontmatter, else the
        post's first image, else a shared placeholder tile. Raster images
        become small WebPs; SVGs are used as they are."""
        choice = post.model.thumbnail
        if choice is False:
            return None
        first = post.first_image
        if choice:
            image = {'src': choice, 'alt': '', 'caption': ''}
            if first and first['src'] == choice:
                image = first          # keep its caption for the enlarged view
        elif first:
            image = first
        else:
            return self.placeholder_thumbnail()
        src = post.source
        source = (src.path if src.is_bundle else src.md_file.parent) / image['src']
        if not source.is_file():
            return None                # already reported as a missing image
        large_size = (THUMB_LARGE_WIDTH, THUMB_LARGE_WIDTH * THUMB_SIZE[1] // THUMB_SIZE[0])
        if source.suffix.lower() == '.svg':
            url = large_url = post.url + image['src']       # vector: one file at any size
        else:
            url, large_url = post.url + 'thumb.webp', post.url + 'thumb-large.webp'
            origin = f"{BuildEnvironment.pretty_path(post.source.md_file)} (thumbnail)"
            for this_url, size in ((url, (THUMB_SIZE[0] * THUMB_SCALE, THUMB_SIZE[1] * THUMB_SCALE)),
                                   (large_url, large_size)):
                if this_url in self.written:
                    BuildEnvironment.emit_error(f"{this_url}: produced by both {self.written[this_url]} and {origin}.")
                    return None
                self.written[this_url] = origin
                target = self._target(this_url)
                if target is None or not write_thumbnail(source, target, self.config.cache_dir, size):
                    BuildEnvironment.emit_warning(f"{origin}: couldn't read {image['src']}; no thumbnail.")
                    return None
        return {
            'url': url,
            'large_url': large_url,
            'small_px': THUMB_SIZE[0] * THUMB_SCALE,
            'large_px': large_size[0],
            'placeholder': False,
            'svg': source.suffix.lower() == '.svg',
            'width': THUMB_SIZE[0],
            'height': THUMB_SIZE[1],
        }

    def placeholder_thumbnail(self) -> dict:
        """The shared thumbnail for posts without an image (written once)."""
        if not hasattr(self, '_placeholder'):
            small = (THUMB_SIZE[0] * THUMB_SCALE, THUMB_SIZE[1] * THUMB_SCALE)
            large = (THUMB_LARGE_WIDTH, THUMB_LARGE_WIDTH * THUMB_SIZE[1] // THUMB_SIZE[0])
            for url, size in (('/thumb-placeholder.webp', small), ('/thumb-placeholder-large.webp', large)):
                self.written[url] = 'the placeholder thumbnail'
                write_placeholder(self._target(url), size, self.config.cache_dir, self.config.icons.get('logo'))
            self._placeholder = {
                'placeholder': True, 'svg': False,
                'url': '/thumb-placeholder.webp', 'large_url': '/thumb-placeholder-large.webp',
                'small_px': small[0], 'large_px': large[0],
                'width': THUMB_SIZE[0], 'height': THUMB_SIZE[1],
            }
        return self._placeholder

    def copy_assets(self, item, origin: str):
        """Copy a post/page folder's other files next to its index.html."""
        src = item.source
        target_dir = self._target(item.url)
        if not src.assets or target_dir is None:
            return
        for rel in src.assets:
            dest = target_dir.parent / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src.path / rel, dest)

    # --- the site --------------------------------------------------------

    def run(self):
        config, site = self.config, self.site
        self.out_dir.mkdir(parents=True, exist_ok=True)

        if config.static_dir.is_dir():
            shutil.copytree(config.static_dir, self.out_dir, dirs_exist_ok=True)
        for path in config.icons.values():
            target = self.out_dir / ICONS_URL.strip('/') / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

        about_photo = config.about.photo if config.about else None
        if about_photo:
            # 2x the displayed size (see .about__photo in styles.css), centre-cropped.
            url = '/images/about-photo.webp'
            self.written[url] = 'the About photo'
            size = (ABOUT_PHOTO_SIZE[0] * 2, ABOUT_PHOTO_SIZE[1] * 2)
            if write_thumbnail(about_photo, self._target(url), config.cache_dir, size):
                self.env.globals['ABOUT_PHOTO'] = url
            else:
                BuildEnvironment.emit_error(f"{BuildEnvironment.pretty_path(about_photo)}: couldn't read the About photo.")

        self.site_card = self.card(
            # The large layout: just the site title and the domain.
            Card(kicker='', title=config.title, large=True, domain=config.domain),
            '/og-card.png', 'the site social card')

        if config.thumbnails:
            for post in site.posts:
                post.thumbnail = self.thumbnail(post)

        for post in site.posts:
            origin = str(BuildEnvironment.pretty_path(post.source.md_file))
            series = (f"{post.series.name} · Part {post.series_part} of {len(post.series.posts)}"
                      if post.series else '')
            card = Card(kicker=config.title, title=post.title, accent_line=series,
                        detail_line=f"{self.env.filters['longdate'](post.date)} · {post.reading_time} min read",
                        domain=config.domain)
            og = self.og(post.url, type='article', title=post.title, description=post.meta_description,
                         image_alt=post.title, published=post.iso_date, tags=[t.name for t in post.tags],
                         **self.og_image(post, card, origin))
            self.render('post.html', post.url, origin, section='/', og=og, lastmod=post.iso_date, post=post)
            self.copy_assets(post, origin)

        for page in site.pages:
            origin = str(BuildEnvironment.pretty_path(page.source.md_file))
            card = Card(kicker=config.title, title=page.title, domain=config.domain)
            og = self.og(page.url, title=page.title, description=page.meta_description,
                         image_alt=page.title, **self.og_image(page, card, origin))
            self.render('page.html', page.url, origin, section=page.url, og=og, page=page)
            self.copy_assets(page, origin)

        self.render_list('index.html', site.posts, '/', 'the front page', section='/')

        for tag in site.tags:
            self.render_list('tag.html', tag.posts, tag.url, f"tag {tag.name!r}", section='/tags/', tag=tag,
                             og_overrides={'title': f"Entries tagged “{tag.name}”",
                                           'description': tag.description or config.description})
        self.render('tags.html', '/tags/', 'the tags index', section='/tags/')

        for series in site.series:
            self.render_list('series.html', series.posts, series.url, f"series {series.name!r}",
                             section='/series/', series=series,
                             og_overrides={'title': f"Series: {series.name}",
                                           'description': series.description or config.description})
        self.render('series_index.html', '/series/', 'the series index', section='/series/')

        # The 404 page gets a small post index so it can send typo'd or
        # wrong-date post URLs to the right post (see templates/404.html).
        post_index = [{'url': p.url, 'date': p.iso_date, 'slug': p.slug, 'title': p.title}
                      for p in site.posts]
        self.render('404.html', '/404.html', 'the 404 page', sitemap=False, post_index=post_index)
        self.write('/feed.xml', self.feed(), 'the RSS feed')
        self.write_json('/data/posts.json', [post_dict(p) for p in site.posts])
        self.write_json('/data/tags.json', [group_dict(t) for t in site.tags])
        self.write_json('/data/series.json', [group_dict(s) for s in site.series])

        # Redirects last, so their targets can be checked against everything built.
        for redirect in site.redirects:
            self.render('redirect.html', redirect.url, f"redirect from {redirect.url}", sitemap=False,
                        target=redirect.target)
        self.check_redirect_targets()

        self.write('/sitemap.xml', self.sitemap_xml(), 'the sitemap')
        if not (self.out_dir / 'robots.txt').exists():      # a robots.txt in static/ wins
            self.write('/robots.txt', f"User-agent: *\nAllow: /\n\nSitemap: {config.url}/sitemap.xml\n",
                       'robots.txt')

        # Last: every link in the finished site must resolve.
        check_links(self.out_dir, self.config.url)

    def check_redirect_targets(self):
        where = BuildEnvironment.pretty_path(self.config.redirects_file)
        for redirect in self.site.redirects:
            if not redirect.target.startswith('/'):
                continue  # external URL: can't check
            path = redirect.target.split('#', 1)[0].split('?', 1)[0]
            if not path.endswith('/') and (self.out_dir / path.lstrip('/')).is_dir():
                path += '/'
            target = self._target(path)
            if target is not None and not target.is_file():
                BuildEnvironment.emit_error(
                    f"{where} [{redirect.url!r}]: target {redirect.target!r} doesn't exist in the built site."
                )

    def render_list(self, template, posts, base_url, origin, og_overrides=None, **context):
        for pagination in paginate(posts, base_url, self.config.posts_per_page):
            label = origin if pagination.number == 1 else f"{origin}, page {pagination.number}"
            og = self.og(pagination.url, **(og_overrides or {}))
            newest = max((p.iso_date for p in pagination.items), default=None)
            self.render(template, pagination.url, label, og=og, lastmod=newest,
                        pagination=pagination, **context)

    def write_json(self, url, data):
        self.write(url, json.dumps(data, indent=2, ensure_ascii=False) + '\n', url)

    def sitemap_xml(self) -> str:
        """Every indexable page. Posts and post lists carry the date of their
        (newest) post; the tags and series indexes the newest post overall."""
        newest = self.site.posts[0].iso_date if self.site.posts else None
        entries = []
        for url, lastmod in sorted(self.sitemap):
            lastmod = lastmod or (newest if url in ('/tags/', '/series/') else None)
            entries.append(f"  <url><loc>{xml_escape(self.config.url + url)}</loc>"
                           + (f"<lastmod>{lastmod}</lastmod>" if lastmod else '') + "</url>")
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "\n".join(entries) + "\n</urlset>\n")

    def feed(self) -> str:
        config = self.config
        items = []
        for post in self.site.posts[:config.feed_items]:
            link = config.url + post.url
            pub = format_datetime(dt.datetime.combine(post.date, dt.time(), dt.timezone.utc))
            items.append(
                "  <item>\n"
                f"    <title>{xml_escape(post.title)}</title>\n"
                f"    <link>{xml_escape(link)}</link>\n"
                f"    <guid>{xml_escape(link)}</guid>\n"
                f"    <pubDate>{pub}</pubDate>\n"
                + "".join(f"    <category>{xml_escape(t.name)}</category>\n" for t in post.tags)
                + f"    <description>{xml_escape(feed_html(post.html, link, config.url))}</description>\n"
                "  </item>"
            )
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<rss version="2.0">\n<channel>\n'
            f"  <title>{xml_escape(config.title)}</title>\n"
            f"  <link>{xml_escape(config.url)}/</link>\n"
            f"  <description>{xml_escape(config.description)}</description>\n"
            + "\n".join(items) + "\n</channel>\n</rss>\n"
        )


ROOT_LINK_RE = re.compile(r'(\b(?:href|src)=")/(?!/)')


def feed_html(html: str, post_link: str, site_url: str) -> str:
    """Post HTML for the feed, with every link absolute: feed readers show
    it away from the site, so "pic.png" and "/other-post/" would break."""
    html = absolutize_links(html, post_link)
    return ROOT_LINK_RE.sub(lambda m: f"{m.group(1)}{site_url}/", html)


def post_dict(post) -> dict:
    return {
        'title': post.title,
        'slug': post.slug,
        'date': post.iso_date,
        'url': post.url,
        'description': post.description,
        'reading_time': post.reading_time,
        'tags': [{'name': t.name, 'slug': t.slug} for t in post.tags],
        'series': post.series and {
            'name': post.series.name, 'slug': post.series.slug, 'part': post.series_part,
        },
    }


def group_dict(group) -> dict:
    return {
        'name': group.name,
        'slug': group.slug,
        'url': group.url,
        'description': group.description,
        'count': len(group.posts),
        'posts': [p.url for p in group.posts],
    }

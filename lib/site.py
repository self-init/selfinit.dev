"""The assembled site: posts and pages linked to their tags, series and
neighbours, ready for rendering.

The models in lib/data are frozen, parsed-from-disk data. The classes here
wrap them with the relationships that only exist once everything is loaded
(older/newer post, series position, posts per tag) and with derived values
(rendered HTML, summary, reading time).
"""
import re
from html import unescape as html_unescape
from functools import cached_property

from markupsafe import Markup, escape

from .build_environment import BuildEnvironment
from .config import SiteConfig
from .data.page_model import PageModel
from .markdown import md
from .data.post_model import PostModel
from .data.redirect_model import RedirectModel
from .data.registry_model import SeriesModel, TagModel
from .sources.content_source import ContentSource
from .sources.registry_source import RegistrySource


FIRST_P_RE = re.compile(r'<p>.*?</p>', re.DOTALL)
TAG_RE = re.compile(r'<[^>]+>')
# Figures (image + caption) and stray <img> tags, removed from summaries
# that have a thumbnail.
IMAGE_HTML_RE = re.compile(r'<figure>.*?</figure>\s*|<img\b[^>]*>', re.DOTALL)
MAX_DESCRIPTION = 200
TRUNCATE_RE = re.compile(r'^[ \t]*<!--\s*truncate\s*-->[ \t]*$', re.MULTILINE | re.IGNORECASE)
# href/src values relative to the page they're on ("pic.png", "./slides.pdf"):
# not absolute URLs, root-relative paths, fragments or other schemes.
RELATIVE_LINK_RE = re.compile(r'(\b(?:href|src)=")(?![a-zA-Z][a-zA-Z0-9+.-]*:|/|#)(?:\./)?([^"]*)"')


def absolutize_links(html: str, base: str) -> str:
    """Rewrite links relative to a post's folder so they still work when
    its HTML appears elsewhere (post lists, the RSS feed). `base` is the
    post's URL, e.g. "/2026-11-09/talk/" or "https://site/2026-11-09/talk/"."""
    return RELATIVE_LINK_RE.sub(lambda m: f'{m.group(1)}{base}{m.group(2)}"', html)
WORDS_PER_MINUTE = 230


class _Content:
    """Shared by posts and pages: delegates model fields, renders Markdown."""

    def __init__(self, model):
        self.model = model

    def __getattr__(self, name):            # title, slug, url, description, source, ...
        return getattr(self.model, name)

    def render_markdown(self, text: str) -> str:
        src = self.model.source
        env = {'base_dir': src.path if src.is_bundle else src.md_file.parent,
               'where': BuildEnvironment.pretty_path(src.md_file)}
        return md.render(text, env)

    @cached_property
    def html(self) -> Markup:
        return Markup(self.render_markdown(self.model.body))

    @property
    def meta_description(self) -> str:
        """Plain-text description for <meta> tags and social previews: the
        `description` frontmatter, or the start of the first paragraph."""
        if self.model.description:
            return self.model.description
        first = FIRST_P_RE.search(self.html)
        text = ' '.join(html_unescape(TAG_RE.sub('', first.group(0))).split()) if first else ''
        if len(text) > MAX_DESCRIPTION:
            text = text[:MAX_DESCRIPTION].rsplit(' ', 1)[0].rstrip(',.;:') + '…'
        return text


class Post(_Content):
    model: PostModel

    def __init__(self, model: PostModel):
        super().__init__(model)
        self.tags: list[Tag] = []
        self.series: Series | None = None
        self.series_part: int | None = None
        self.series_prev: Post | None = None
        self.series_next: Post | None = None
        self.older: Post | None = None
        self.newer: Post | None = None
        self.thumbnail: dict | None = None  # set by the renderer when thumbnails are on

    @cached_property
    def first_image(self) -> dict | None:
        """The first image in the post stored next to it (relative path):
        {'src', 'alt', 'caption'}. Remote images are skipped."""
        for token in md.parse(self.model.body):
            for child in token.children or []:
                src = str(child.attrs.get('src', '')) if child.type == 'image' else ''
                if src and not re.match(r'^([a-zA-Z][a-zA-Z0-9+.-]*:|/)', src):
                    title = child.attrs.get('title')
                    return {'src': src.removeprefix('./'), 'alt': child.content,
                            'caption': md.renderInline(str(title)) if title else ''}
        return None

    @property
    def iso_date(self) -> str:
        return self.model.date.isoformat()

    @property
    def reading_time(self) -> int:
        """Estimated minutes to read."""
        return max(1, round(len(self.model.body.split()) / WORDS_PER_MINUTE))

    @property
    def summary_html(self) -> Markup:
        """Teaser for post lists, first match wins:
          1. everything above a `<!-- truncate -->` line in the post;
          2. the `description` frontmatter;
          3. the post's first paragraph.
        Relative links/images are rewritten to point into the post's folder.
        With a thumbnail, images are left out (the thumbnail stands in)."""
        marker = TRUNCATE_RE.search(self.model.body)
        if marker:
            excerpt = self.render_markdown(self.model.body[:marker.start()])
            if self.thumbnail:
                excerpt = IMAGE_HTML_RE.sub('', excerpt).strip()
            if excerpt:
                return Markup(absolutize_links(excerpt, self.url))
        if self.model.description:
            return Markup(f"<p>{escape(self.model.description)}</p>")
        first = FIRST_P_RE.search(self.html)
        return Markup(absolutize_links(first.group(0), self.url)) if first else Markup('')


class Page(_Content):
    model: PageModel


class _Group:
    """A tag or series: a registry entry plus the posts that use it."""

    def __init__(self, model):
        self.model = model
        self.posts: list[Post] = []

    def __getattr__(self, name):            # name, slug, description, url
        return getattr(self.model, name)


class Tag(_Group):
    """Posts newest first."""


class Series(_Group):
    """Posts in reading order: oldest first, so part 1 is the earliest."""

    @property
    def latest(self) -> Post:
        return self.posts[-1]


class Site:
    def __init__(self, config: SiteConfig, posts, pages, tags, series, redirects, drafts_skipped):
        self.config = config
        self.posts: list[Post] = posts          # newest first
        self.pages: list[Page] = pages
        self.tags: list[Tag] = tags             # only tags that have posts, A-Z
        self.series: list[Series] = series      # only series that have posts, A-Z
        self.redirects: list[RedirectModel] = redirects
        self.drafts_skipped = drafts_skipped

    @classmethod
    def load(cls, config: SiteConfig, include_drafts: bool = False) -> 'Site':
        tag_models = TagModel.from_sources(RegistrySource.discover([config.tags_file]))
        series_models = SeriesModel.from_sources(RegistrySource.discover([config.series_file]))
        redirects = (RedirectModel.from_sources(RegistrySource.discover([config.redirects_file]))
                     if config.redirects_file.exists() else [])

        post_models, page_models = [], []
        for collection in config.collections:
            sources = ContentSource.discover([collection.path])
            if collection.model == 'post':
                post_models += PostModel.from_sources(sources, collection=collection)
            else:
                page_models += PageModel.from_sources(sources, collection=collection)

        drafts = [m for m in post_models + page_models if m.draft]
        if not include_drafts:
            post_models = [m for m in post_models if not m.draft]
            page_models = [m for m in page_models if not m.draft]

        posts = sorted((Post(m) for m in post_models), key=lambda p: (p.date, p.title), reverse=True)
        pages = [Page(m) for m in page_models]
        tags = _attach(posts, tag_models, Tag, 'tag', config.tags_file,
                       lambda post: post.model.tags, lambda post, tag: post.tags.append(tag))
        series = _attach(posts, series_models, Series, 'series', config.series_file,
                         lambda post: [post.model.series] if post.model.series else [],
                         lambda post, s: setattr(post, 'series', s))

        for newer, older in zip(posts, posts[1:]):
            newer.older, older.newer = older, newer
        for s in series:
            s.posts.reverse()   # _attach adds newest first; series read oldest first
            for i, post in enumerate(s.posts):
                post.series_part = i + 1
                post.series_prev = s.posts[i - 1] if i > 0 else None
                post.series_next = s.posts[i + 1] if i + 1 < len(s.posts) else None

        skipped = 0 if include_drafts else len(drafts)
        return cls(config, posts, pages, tags, series, redirects, skipped)


def _attach(posts, models, group_cls, kind, registry_file, names_of, link):
    """Resolve each post's tag/series names against the registry (unknown
    names are errors) and return the groups that have posts, A-Z."""
    by_name = {m.name: group_cls(m) for m in models}
    registry = BuildEnvironment.pretty_path(registry_file)
    for post in posts:
        for name in names_of(post):
            group = by_name.get(name)
            if group is None:
                BuildEnvironment.emit_error(
                    f"{BuildEnvironment.pretty_path(post.source.md_file)}: {kind} {name!r} "
                    f"is not in {registry}. Add it there, or fix the spelling."
                )
                continue
            group.posts.append(post)
            link(post, group)
    return sorted((g for g in by_name.values() if g.posts), key=lambda g: g.name.lower())

"""Site configuration (site.json): site details, icons, navigation, and the
collections that tell the build where to find posts and pages."""
import json
from dataclasses import dataclass
from pathlib import Path
from string import Formatter

from .build_environment import BuildEnvironment
from .fields import get_field, get_int, get_str, warn_unknown_keys

MODELS = ('post', 'page')

# Placeholders allowed in each model's URL pattern, and the defaults.
URL_FIELDS = {
    'post': {'date', 'year', 'month', 'day', 'slug'},
    'page': {'slug'},
}
DEFAULT_URLS = {'post': '/{date}/{slug}/', 'page': '/{slug}/'}

ICON_NAMES = ('logo', 'favicon', 'pattern')

# Desktop post-list layouts with thumbnails (phones always stack them):
#   beside: thumbnail left of the title/dateline/summary, footer row underneath
#   column: thumbnail with the dateline, tags, series and Read more under it;
#           title and summary on the right
THUMBNAIL_LAYOUTS = ('beside', 'column')
NAV_MENUS = ('recent', 'series', 'tags')     # nav "menu": automatic dropdown lists

TOP_LEVEL_KEYS = {
    'title', 'description', 'url', 'author', 'about',
    'recent_posts', 'posts_per_page', 'feed_items',
    'icons', 'nav', 'collections',
    'tags', 'series', 'redirects', 'static', 'templates', 'output',
    'social_cards', 'thumbnails', 'thumbnail_layout', 'fonts', 'cache', 'comments',
}


@dataclass(frozen=True)
class NavItem:
    label: str
    url: str | None                 # None: a dropdown parent that isn't a link
    children: tuple['NavItem', ...] = ()
    menu: str | None = None         # automatic dropdown: 'recent' posts, 'series' or 'tags'

    def is_current(self, section: str | None) -> bool:
        return section is not None and (
            self.url == section or any(child.url == section for child in self.children)
        )


@dataclass(frozen=True)
class About:
    """The sidebar's About section."""
    text: str
    photo: Path | None = None               # source image; resized by the build
    links: tuple[NavItem, ...] = ()         # e.g. GitHub, LinkedIn, Email
    page: str | None = None                 # "More about me »" link


@dataclass(frozen=True)
class Comments:
    """giscus comments (https://giscus.app), backed by GitHub Discussions.
    The IDs come from giscus.app's configuration page (or the GitHub API)."""
    repo: str                       # "owner/name"
    repo_id: str
    category: str
    category_id: str
    reactions: bool = True
    input_position: str = 'top'     # comment box above ('top') or below the comments
    lang: str = 'en'
    theme: str = 'light'            # built-in giscus theme, or a site path like "/giscus-theme.css"
    theme_dark: str = 'dark'        # the same, for the site's dark theme


@dataclass(frozen=True)
class Collection:
    """Where to find content of one model, and the URL pattern for it.

    `path` is a directory (each .md file or single-.md folder inside is one
    item) or a single .md file / folder.
    """
    model: str          # 'post' or 'page'
    path: Path
    url: str            # e.g. '/{date}/{slug}/'


@dataclass(frozen=True)
class SiteConfig:
    file: Path
    root: Path
    title: str
    description: str
    url: str
    author: str
    about: About
    recent_posts: int
    posts_per_page: int
    feed_items: int
    icons: dict[str, Path]          # name -> source file; missing = no icon
    nav: tuple[NavItem, ...]
    collections: tuple[Collection, ...]
    tags_file: Path
    series_file: Path
    redirects_file: Path            # optional: missing file = no redirects
    static_dir: Path
    templates_dir: Path
    output_dir: Path
    social_cards: bool              # generate Open Graph card images
    thumbnails: bool                # small images beside posts in lists
    thumbnail_layout: str           # 'beside' or 'column' (desktop post-list layout)
    fonts_dir: Path                 # fonts for generated images (IBM Plex Mono)
    cache_dir: Path                 # generated images are cached here between builds
    comments: Comments | None       # None: no comment sections

    @property
    def domain(self) -> str:
        return self.url.split('://', 1)[-1].rstrip('/')


def load_config(path: Path) -> SiteConfig | None:
    """Parse and validate site.json. Paths in it are relative to its folder.
    Returns None (after emitting errors) if anything is invalid."""
    where = str(BuildEnvironment.pretty_path(path))
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        BuildEnvironment.emit_error(f"{where}: config file not found.")
        return None
    except json.JSONDecodeError as e:
        BuildEnvironment.emit_error(f"{where}: invalid JSON: {e}")
        return None
    if not isinstance(data, dict):
        BuildEnvironment.emit_error(f"{where}: must contain a JSON object.")
        return None

    errors_before = len(BuildEnvironment.errors)
    root = path.resolve().parent
    warn_unknown_keys(data, TOP_LEVEL_KEYS, where)

    title = get_str(data, 'title', where)
    description = get_str(data, 'description', where, default='')
    url = get_str(data, 'url', where)
    if url and not url.startswith(('http://', 'https://')):
        BuildEnvironment.emit_error(f"{where}: 'url' must start with http:// or https://.")

    config = dict(
        file=path.resolve(),
        root=root,
        title=title,
        description=description,
        url=url.rstrip('/') if url else url,
        author=get_str(data, 'author', where, default=title or ''),
        about=_load_about(data, root, where, default_text=description or ''),
        recent_posts=get_int(data, 'recent_posts', where, default=5, minimum=0),
        posts_per_page=get_int(data, 'posts_per_page', where, default=10, minimum=1),
        feed_items=get_int(data, 'feed_items', where, default=20, minimum=1),
        icons=_load_icons(data, root, where),
        nav=_load_nav(data, where),
        collections=_load_collections(data, root, where),
        tags_file=root / (get_str(data, 'tags', where, default='tags.json') or 'tags.json'),
        series_file=root / (get_str(data, 'series', where, default='series.json') or 'series.json'),
        redirects_file=root / (get_str(data, 'redirects', where, default='redirects.json') or 'redirects.json'),
        static_dir=root / (get_str(data, 'static', where, default='static') or 'static'),
        templates_dir=root / (get_str(data, 'templates', where, default='templates') or 'templates'),
        output_dir=root / (get_str(data, 'output', where, default='output') or 'output'),
        social_cards=get_field(data, 'social_cards', bool, where, default=True),
        thumbnails=get_field(data, 'thumbnails', bool, where, default=False),
        thumbnail_layout=_choice(data, 'thumbnail_layout', THUMBNAIL_LAYOUTS, where),
        fonts_dir=root / (get_str(data, 'fonts', where, default='fonts') or 'fonts'),
        cache_dir=root / (get_str(data, 'cache', where, default='.cache') or '.cache'),
        comments=_load_comments(data, where),
    )

    if not config['templates_dir'].is_dir():
        BuildEnvironment.emit_error(f"{where}: templates folder {config['templates_dir']} not found.")

    if len(BuildEnvironment.errors) > errors_before:
        return None
    return SiteConfig(**config)


def _choice(data, key, options, where):
    value = get_str(data, key, where, default=options[0])
    if value is not None and value not in options:
        BuildEnvironment.emit_error(f"{where}: '{key}' must be one of {', '.join(options)}, not {value!r}.")
        return None
    return value


def _load_about(data, root, where, default_text) -> About | None:
    """'about' is either plain text, or an object:
        {"text": "...", "photo": "images/me.jpg",
         "links": [{"label": "GitHub", "url": "https://..."}], "page": "/about/"}"""
    raw = data.get('about', default_text)
    if isinstance(raw, str):
        return About(text=raw)
    if not isinstance(raw, dict):
        BuildEnvironment.emit_error(f"{where}: 'about' must be text or an object with 'text'.")
        return None
    here = f"{where} about"
    warn_unknown_keys(raw, ('text', 'photo', 'links', 'page'), here)
    text = get_str(raw, 'text', here, default=default_text)
    photo = get_str(raw, 'photo', here, default=None)
    if photo is not None and not (root / photo).is_file():
        BuildEnvironment.emit_error(f"{here}: photo '{photo}' not found.")
        photo = None
    links = []
    for i, item in enumerate(get_field(raw, 'links', list, here, default=[]) or []):
        link = _load_nav_item(item, f"{here} links[{i}]", depth=1)
        if link and link.url is None:
            BuildEnvironment.emit_error(f"{here} links[{i}]: needs a 'url'.")
        elif link:
            links.append(link)
    page = get_str(raw, 'page', here, default=None)
    return About(text=text or '', photo=root / photo if photo else None, links=tuple(links), page=page)


def _load_comments(data, where) -> Comments | None:
    """Optional "comments": {"repo", "repo_id", "category", "category_id",
    "reactions", "input_position", "lang", "theme", "theme_dark"}. Missing IDs leave
    comments off with a warning, so they can be filled in later."""
    raw = get_field(data, 'comments', dict, where, default=None)
    if not raw:
        return None
    here = f"{where} comments"
    keys = ('repo', 'repo_id', 'category', 'category_id', 'reactions', 'input_position', 'lang', 'theme', 'theme_dark')
    warn_unknown_keys(raw, keys, here)
    required = {k: get_str(raw, k, here, default='') for k in keys[:4]}
    missing = [k for k, v in required.items() if not v]
    if missing:
        verb = 'is' if len(missing) == 1 else 'are'
        BuildEnvironment.emit_warning(f"{here}: comments are off until {', '.join(missing)} {verb} set.")
        return None
    position = get_str(raw, 'input_position', here, default='top')
    if position not in ('top', 'bottom'):
        BuildEnvironment.emit_error(f"{here}: 'input_position' must be top or bottom.")
    return Comments(
        **required,
        reactions=get_field(raw, 'reactions', bool, here, default=True),
        input_position=position,
        lang=get_str(raw, 'lang', here, default='en'),
        theme=get_str(raw, 'theme', here, default='light'),
        theme_dark=get_str(raw, 'theme_dark', here, default='dark'),
    )


def _load_icons(data, root, where) -> dict[str, Path]:
    icons = get_field(data, 'icons', dict, where, default={}) or {}
    where = f"{where} icons"
    warn_unknown_keys(icons, ICON_NAMES, where)
    result = {}
    for name in ICON_NAMES:
        file = get_str(icons, name, where, default=None)
        if file is None:
            continue  # absent or null: that icon is turned off
        source = root / file
        if not source.is_file():
            BuildEnvironment.emit_error(f"{where}: {name} file '{file}' not found.")
            continue
        result[name] = source
    return result


def _load_nav(data, where) -> tuple[NavItem, ...]:
    items = get_field(data, 'nav', list, where, default=[{'label': 'Posts', 'url': '/'}]) or []
    return tuple(item for i, raw in enumerate(items)
                 if (item := _load_nav_item(raw, f"{where} nav[{i}]", depth=0)))


def _load_nav_item(raw, where, depth) -> NavItem | None:
    if not isinstance(raw, dict):
        BuildEnvironment.emit_error(f"{where}: must be an object with 'label' and 'url'.")
        return None
    warn_unknown_keys(raw, ('label', 'url', 'children', 'menu'), where)
    label = get_str(raw, 'label', where)
    url = get_str(raw, 'url', where, default=None)
    children_raw = get_field(raw, 'children', list, where, default=[]) or []
    menu = get_str(raw, 'menu', where, default=None)
    if menu is not None and menu not in NAV_MENUS:
        BuildEnvironment.emit_error(f"{where}: 'menu' must be one of {', '.join(NAV_MENUS)}.")
        return None
    if menu and (children_raw or depth > 0):
        BuildEnvironment.emit_error(f"{where}: 'menu' can't be combined with 'children' or used inside a dropdown.")
        return None

    if children_raw and depth > 0:
        BuildEnvironment.emit_error(f"{where}: dropdowns can only be one level deep.")
        return None
    children = tuple(child for i, c in enumerate(children_raw)
                     if (child := _load_nav_item(c, f"{where}.children[{i}]", depth + 1)))
    if url is None and not children_raw:
        BuildEnvironment.emit_error(f"{where}: needs a 'url' (or 'children' for a dropdown).")
        return None
    if url is not None and not url.startswith(('/', 'http://', 'https://', 'mailto:')):
        BuildEnvironment.emit_error(f"{where}: 'url' must start with /, http(s):// or mailto:.")
        return None
    return NavItem(label, url, children, menu) if label else None


def _load_collections(data, root, where) -> tuple[Collection, ...]:
    default = [{'model': 'post', 'path': 'posts'}]
    items = get_field(data, 'collections', list, where, default=default) or []
    collections = []
    for i, raw in enumerate(items):
        here = f"{where} collections[{i}]"
        if not isinstance(raw, dict):
            BuildEnvironment.emit_error(f"{here}: must be an object with 'model' and 'path'.")
            continue
        warn_unknown_keys(raw, ('model', 'path', 'url'), here)
        model = get_str(raw, 'model', here)
        path = get_str(raw, 'path', here)
        if model is None or path is None:
            continue
        if model not in MODELS:
            BuildEnvironment.emit_error(f"{here}: 'model' must be one of {', '.join(MODELS)}, not {model!r}.")
            continue
        url = get_str(raw, 'url', here, default=DEFAULT_URLS[model])
        if url is None or not _valid_url_pattern(url, model, here):
            continue
        if not (root / path).exists():
            BuildEnvironment.emit_error(f"{here}: path '{path}' not found.")
            continue
        collections.append(Collection(model, root / path, url))
    return tuple(collections)


def _valid_url_pattern(url, model, where) -> bool:
    if not (url.startswith('/') and url.endswith('/')):
        BuildEnvironment.emit_error(f"{where}: 'url' must start and end with /, e.g. {DEFAULT_URLS[model]!r}.")
        return False
    try:
        names = {name for _, name, _, _ in Formatter().parse(url) if name is not None}
    except ValueError as e:
        BuildEnvironment.emit_error(f"{where}: invalid 'url' pattern {url!r}: {e}")
        return False
    unknown = names - URL_FIELDS[model]
    if unknown:
        allowed = ', '.join('{' + n + '}' for n in sorted(URL_FIELDS[model]))
        BuildEnvironment.emit_error(
            f"{where}: unknown placeholder(s) {', '.join(sorted(unknown))} in 'url'; {model} URLs can use {allowed}."
        )
        return False
    return True

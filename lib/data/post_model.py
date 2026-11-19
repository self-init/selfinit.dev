import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..build_environment import BuildEnvironment
from ..config import Collection
from ..fields import get_field, get_slug, get_str, warn_unknown_keys
from ..sources.content_source import ContentSource
from .content import load_markdown, og_image as _og_image, strip_title_heading, thumbnail as _thumbnail
from .model import Model

DATE_PREFIX_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})')

FRONTMATTER_KEYS = ('title', 'slug', 'date', 'description', 'tags', 'series', 'draft', 'og_image', 'thumbnail', 'comments', 'discussion')


@dataclass(frozen=True)
class PostModel(Model):
    """A dated blog post.

    Frontmatter: title (required), date (required unless the file/folder
    name starts with YYYY-MM-DD), slug (default: from the title),
    description, tags (list; each must be in the tag registry), series
    (must be in the series registry), draft (true: left out of the build).
    """
    source: ContentSource
    title: str
    slug: str
    date: dt.date
    description: str
    tags: tuple[str, ...]
    series: str | None
    draft: bool
    og_image: str | None    # social preview image, relative to the post/page
    thumbnail: str | bool | None  # list thumbnail: path, False = none, None = first image
    comments: bool          # false: no comment section on this post
    discussion: int | None  # existing GitHub Discussion number to show (e.g. migrated threads)
    body: str           # Markdown, minus a leading heading that repeats the title
    url: str

    @classmethod
    def from_source(cls, src: ContentSource, *, collection: Collection, **_) -> Sequence[Self]:
        where = str(BuildEnvironment.pretty_path(src.md_file))
        post = load_markdown(src)
        if post is None:
            return []
        meta = post.metadata
        errors_before = len(BuildEnvironment.errors)
        warn_unknown_keys(meta, FRONTMATTER_KEYS, where)

        title = get_str(meta, 'title', where)
        slug = get_slug(meta, 'slug', where, title)
        date = _post_date(meta, src, where)
        description = get_str(meta, 'description', where, default='')
        tags = _tags(meta, where)
        series = get_str(meta, 'series', where, default=None)
        draft = get_field(meta, 'draft', bool, where, default=False)
        og_image = _og_image(meta, src, where)
        thumbnail = _thumbnail(meta, src, where)
        comments = get_field(meta, 'comments', bool, where, default=True)
        discussion = get_field(meta, 'discussion', int, where, default=None)

        if len(BuildEnvironment.errors) > errors_before:
            return []
        url = collection.url.format(
            date=date.isoformat(), year=f"{date.year:04}", month=f"{date.month:02}",
            day=f"{date.day:02}", slug=slug,
        )
        return [cls(
            source=src, title=title, slug=slug, date=date, description=description,
            tags=tags, series=series, draft=draft, og_image=og_image, thumbnail=thumbnail,
            comments=comments, discussion=discussion,
            body=strip_title_heading(post.content, title), url=url,
        )]


def _post_date(meta, src: ContentSource, where) -> dt.date | None:
    value = meta.get('date')
    if value is None:
        match = DATE_PREFIX_RE.match(src.path.name)
        if not match:
            BuildEnvironment.emit_error(
                f"{where}: no date. Add `date: YYYY-MM-DD` to the frontmatter, "
                f"or start the file/folder name with YYYY-MM-DD."
            )
            return None
        value = match.group(1)
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        BuildEnvironment.emit_error(f"{where}: 'date' {value!r} is not a valid YYYY-MM-DD date.")
        return None


def _tags(meta, where) -> tuple[str, ...]:
    tags = meta.get('tags', [])
    if isinstance(tags, str):
        tags = [tags]
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
        BuildEnvironment.emit_error(f"{where}: 'tags' must be a list of tag names, e.g. `tags: [ssh, security]`.")
        return ()
    return tuple(dict.fromkeys(t.strip() for t in tags))  # de-duplicated, order kept

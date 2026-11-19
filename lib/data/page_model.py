from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..build_environment import BuildEnvironment
from ..config import Collection
from ..fields import get_field, get_slug, get_str, warn_unknown_keys
from ..sources.content_source import ContentSource
from .content import load_markdown, og_image as _og_image, strip_title_heading
from .model import Model

FRONTMATTER_KEYS = ('title', 'slug', 'description', 'draft', 'og_image', 'sidebar')


@dataclass(frozen=True)
class PageModel(Model):
    """A standalone page (About, etc.): no date, tags or series.

    Frontmatter: title (required), slug (default: from the title),
    description, draft (true: left out of the build), og_image, sidebar
    (false: no sidebar on this page).
    """
    source: ContentSource
    title: str
    slug: str
    description: str
    draft: bool
    og_image: str | None    # social preview image, relative to the post/page
    sidebar: bool
    body: str
    url: str

    @classmethod
    def from_source(cls, src: ContentSource, *, collection: Collection, **_) -> Sequence[Self]:
        where = str(BuildEnvironment.pretty_path(src.md_file))
        page = load_markdown(src)
        if page is None:
            return []
        meta = page.metadata
        errors_before = len(BuildEnvironment.errors)
        warn_unknown_keys(meta, FRONTMATTER_KEYS, where)

        title = get_str(meta, 'title', where)
        slug = get_slug(meta, 'slug', where, title)
        description = get_str(meta, 'description', where, default='')
        draft = get_field(meta, 'draft', bool, where, default=False)
        og_image = _og_image(meta, src, where)
        sidebar = get_field(meta, 'sidebar', bool, where, default=True)

        if len(BuildEnvironment.errors) > errors_before:
            return []
        return [cls(
            source=src, title=title, slug=slug, description=description, draft=draft, og_image=og_image, sidebar=sidebar,
            body=strip_title_heading(page.content, title),
            url=collection.url.format(slug=slug),
        )]

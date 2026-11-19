from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Self

from ..build_environment import BuildEnvironment
from ..fields import get_slug, get_str, warn_unknown_keys
from ..sources.registry_source import RegistrySource
from .model import Model


@dataclass(frozen=True)
class RegistryModel(Model):
    """An entry in a registry file. Each name maps to one of:
        "Name": "custom-slug"
        "Name": {"slug": "custom-slug", "description": "Shown on its page."}
        "Name": {}  or  null          (slug made from the name)
    """
    name: str
    slug: str
    description: str

    url_prefix: ClassVar[str]

    @property
    def url(self) -> str:
        return f"{self.url_prefix}{self.slug}/"

    @classmethod
    def from_source(cls, src: RegistrySource, **_) -> Sequence[Self]:
        data = src.load()
        if data is None:
            return []
        pretty = BuildEnvironment.pretty_path(src.path)
        entries, slugs = [], {}
        for name, value in data.items():
            where = f"{pretty} [{name!r}]"
            if isinstance(value, str):
                value = {'slug': value}
            elif value is None:
                value = {}
            elif not isinstance(value, dict):
                BuildEnvironment.emit_error(f"{where}: must be a slug string or an object.")
                continue
            warn_unknown_keys(value, ('slug', 'description'), where)
            slug = get_slug(value, 'slug', where, name)
            description = get_str(value, 'description', where, default='')
            if slug is None or description is None:
                continue
            if slug in slugs:
                BuildEnvironment.emit_error(
                    f"{pretty}: {slugs[slug]!r} and {name!r} would both live at {cls.url_prefix}{slug}/."
                )
                continue
            slugs[slug] = name
            entries.append(cls(name=str(name), slug=slug, description=description))
        return entries


@dataclass(frozen=True)
class TagModel(RegistryModel):
    url_prefix: ClassVar[str] = '/tags/'


@dataclass(frozen=True)
class SeriesModel(RegistryModel):
    url_prefix: ClassVar[str] = '/series/'

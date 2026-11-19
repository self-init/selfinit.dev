from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..build_environment import BuildEnvironment
from ..sources.registry_source import RegistrySource
from .model import Model


@dataclass(frozen=True)
class RedirectModel(Model):
    """One entry of redirects.json: "/old/path/": "/new/url/".

    The old path gets a small page that forwards visitors (keeping any
    #fragment). Paths without a file extension are treated as folders, so
    "/blog/post" and "/blog/post/" both work. The target can be a site path
    (checked to exist after the build) or a full http(s) URL.
    """
    url: str
    target: str

    @classmethod
    def from_source(cls, src: RegistrySource, **_) -> Sequence[Self]:
        data = src.load()
        if data is None:
            return []
        pretty = BuildEnvironment.pretty_path(src.path)
        redirects = []
        for old, new in data.items():
            where = f"{pretty} [{old!r}]"
            if not old.startswith('/') or old.startswith('//'):
                BuildEnvironment.emit_error(f"{where}: old paths must start with a single /, e.g. \"/blog/my-post/\".")
                continue
            if not isinstance(new, str) or not new.startswith(('/', 'http://', 'https://')):
                BuildEnvironment.emit_error(f"{where}: target must be a site path (/...) or an http(s) URL, not {new!r}.")
                continue
            redirects.append(cls(url=as_page_url(old), target=new))
        return redirects


def as_page_url(path: str) -> str:
    """'/blog/post' -> '/blog/post/' (a folder); '/old.html' stays a file."""
    last = path.rstrip('/').rsplit('/', 1)[-1]
    return path if path.endswith('/') or '.' in last else path + '/'

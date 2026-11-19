"""Small helpers for reading typed values out of parsed JSON/YAML/frontmatter,
reporting problems through BuildEnvironment instead of raising."""
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from .build_environment import BuildEnvironment

REQUIRED: Any = object()  # sentinel: the key must be present

SLUG_RE = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

_TYPE_NAMES = {str: 'a string', int: 'a whole number', bool: 'true or false',
               list: 'a list', dict: 'an object'}


def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode()
    text = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return text or 'untitled'


def get_field(data: Mapping, key: str, kind: type, where: str, default: Any = REQUIRED):
    """Return data[key] if it has type `kind`, else emit an error and return
    None. Missing keys return `default`, or error if the key is REQUIRED."""
    if key not in data or data[key] is None:
        if default is REQUIRED:
            BuildEnvironment.emit_error(f"{where}: missing required '{key}'.")
            return None
        return default
    value = data[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        BuildEnvironment.emit_error(
            f"{where}: '{key}' must be {_TYPE_NAMES.get(kind, kind.__name__)}, "
            f"not {type(value).__name__} ({value!r})."
        )
        return None
    return value


def get_str(data: Mapping, key: str, where: str, default: Any = REQUIRED, nonempty=True):
    value = get_field(data, key, str, where, default)
    if isinstance(value, str) and nonempty and not value.strip() and default is REQUIRED:
        BuildEnvironment.emit_error(f"{where}: '{key}' must not be empty.")
        return None
    return value.strip() if isinstance(value, str) else value


def get_int(data: Mapping, key: str, where: str, default: Any = REQUIRED, minimum: int | None = None):
    value = get_field(data, key, int, where, default)
    if isinstance(value, int) and minimum is not None and value < minimum:
        BuildEnvironment.emit_error(f"{where}: '{key}' must be at least {minimum}, not {value}.")
        return None
    return value


def get_slug(data: Mapping, key: str, where: str, fallback_text: str | None):
    """An explicit slug (validated) or one built from `fallback_text`."""
    value = get_str(data, key, where, default=None)
    if value is None:
        return slugify(fallback_text) if fallback_text else None
    if not SLUG_RE.match(value):
        BuildEnvironment.emit_error(
            f"{where}: '{key}' {value!r} must be lowercase letters, digits and single hyphens."
        )
        return None
    return value


def warn_unknown_keys(data: Mapping, known: Iterable[str], where: str):
    """Catch typos like `tag:` for `tags:` that would otherwise be ignored."""
    for key in data:
        if key not in known:
            BuildEnvironment.emit_warning(f"{where}: unknown key '{key}' (ignored).")

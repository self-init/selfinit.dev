import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import yaml

from ..build_environment import BuildEnvironment
from .source import Source

KINDS = {'.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml'}


@dataclass(frozen=True)
class RegistrySource(Source):
    """A registry file (tags, series): JSON, YAML or TOML mapping each name
    to its details."""
    path: Path
    kind: Literal["json", "yaml", "toml"]

    @classmethod
    def from_path(cls, path: Path) -> Self | None:
        pretty = BuildEnvironment.pretty_path(path)
        if not path.is_file():
            BuildEnvironment.emit_warning(f"{pretty}: registry file not found; treating it as empty.")
            return None
        kind = KINDS.get(path.suffix.lower())
        if kind is None:
            BuildEnvironment.emit_error(f"{pretty}: unrecognized registry file type (use .json, .yaml or .toml).")
            return None
        return cls(path=path, kind=kind)

    def load(self) -> dict | None:
        pretty = BuildEnvironment.pretty_path(self.path)
        try:
            text = self.path.read_text(encoding='utf-8')
            if self.kind == 'json':
                data = json.loads(text) if text.strip() else {}
            elif self.kind == 'yaml':
                data = yaml.safe_load(text) or {}
            else:
                data = tomllib.loads(text)
        except (json.JSONDecodeError, yaml.YAMLError, tomllib.TOMLDecodeError) as e:
            BuildEnvironment.emit_error(f"{pretty}: could not parse: {e}")
            return None
        if not isinstance(data, dict):
            BuildEnvironment.emit_error(f"{pretty}: must map names to slugs or objects.")
            return None
        return data

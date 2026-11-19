from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from ..sources.source import Source


@dataclass(frozen=True)
class Model(ABC):
    """Parsed, validated data built from a Source. Invalid input emits
    errors through BuildEnvironment and yields no model."""

    @classmethod
    @abstractmethod
    def from_source(cls, src: Source, **context) -> Sequence[Self]:
        pass

    @classmethod
    def from_sources(cls, srcs: Sequence[Source], **context) -> Sequence[Self]:
        models = []
        for source in srcs:
            models.extend(cls.from_source(source, **context))
        return models

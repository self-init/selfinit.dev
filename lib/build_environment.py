from pathlib import Path


class BuildEnvironment:
    """Collects warnings and errors for the whole build.

    Problems are reported, not raised, so one run lists everything that's
    wrong instead of stopping at the first issue. The build checks
    `has_errors()` between phases and refuses to write output if any were
    emitted.
    """

    warnings: list[str] = []
    errors: list[str] = []

    # Project root; paths in messages are shown relative to it.
    path: Path = Path(__file__).resolve().parent.parent

    @classmethod
    def reset(cls, path: Path | None = None):
        if path is not None:
            cls.path = path.resolve()
        cls.warnings = []
        cls.errors = []

    @classmethod
    def emit_warning(cls, warning: str):
        if warning in cls.warnings:
            return  # e.g. the same Markdown rendered for a post and its summary
        print("[Warning] " + warning)
        cls.warnings.append(warning)

    @classmethod
    def emit_error(cls, error: str):
        if error in cls.errors:
            return
        print("[Error] " + error)
        cls.errors.append(error)

    @classmethod
    def has_errors(cls) -> bool:
        return bool(cls.errors)

    @classmethod
    def pretty_path(cls, path: Path) -> Path:
        try:
            return path.resolve().relative_to(cls.path)
        except ValueError:
            return path

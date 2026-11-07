"""jearless — Fearless. Jearless. Task tracking and a changelog on bare git."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

# The version is DERIVED from package metadata (which pyproject feeds, which the
# hook mirrors) — a hardcoded third copy here would drift, and did (0.1.0 in the
# wheel while the flow lived at 0.10.4). One authored source, everything else derives.
try:
    __version__ = _package_version("jearless")
except PackageNotFoundError:  # running from a bare source tree, not installed
    __version__ = "0.0.0"

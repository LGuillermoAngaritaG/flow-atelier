"""flow-atelier: async workflow engine for running DAG-based conduits."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("flow-atelier")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "0.0.0+dev"

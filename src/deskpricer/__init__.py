from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("deskpricer")
except PackageNotFoundError:
    __version__ = "unknown"

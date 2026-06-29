"""igpsport-mcp: local MCP server for iGPSport cycling data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("igpsport-mcp")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.0.0+dev"

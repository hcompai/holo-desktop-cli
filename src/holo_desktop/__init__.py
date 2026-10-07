"""HoloDesktop CLI: H Company's desktop agent on your machine, a thin shell over the hai-agents SDK local mode."""

from importlib.metadata import version

__version__ = version("holo-desktop-cli")
__all__ = ["__version__"]

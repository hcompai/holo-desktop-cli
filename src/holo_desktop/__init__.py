"""HoloDesktop CLI: thin client to the hai-agent-runtime desktop agent, powered by H Company's Holo3 VLM."""

from importlib.metadata import version

__version__ = version("holo-desktop-cli")
__all__ = ["__version__"]

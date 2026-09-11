"""HoloDesktop CLI: thin client to the hai-agent-runtime desktop agent, powered by H Company's Holo3 VLM."""

from importlib.metadata import version

__version__ = version("holo-desktop-cli")
USER_AGENT = f"holo-desktop-cli/{__version__}"
__all__ = ["USER_AGENT", "__version__"]

"""HoloDesktop CLI: thin client to the hai-agent-runtime desktop agent, powered by H Company's Holo3 VLM."""

import platform
from importlib.metadata import version

__version__ = version("holo-desktop-cli")
USER_AGENT = f"holo-desktop-cli/{__version__}"
CLIENT_HEADERS = {
    "User-Agent": USER_AGENT,
    "X-HCompany-Client-Name": "holo-desktop-cli",
    "X-HCompany-Client-Version": __version__,
    "X-HCompany-Client-Type": "cli",
    "X-HCompany-Language": "Python",
    "X-HCompany-Runtime": f"python/{platform.python_version()}",
    "X-HCompany-Platform": f"{platform.system().lower()}/{platform.release()}",
}
__all__ = ["CLIENT_HEADERS", "USER_AGENT", "__version__"]

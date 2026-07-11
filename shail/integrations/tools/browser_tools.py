import logging
from typing import Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DENY_DOMAINS = [
    "facebook.com", 
    "twitter.com", 
    "x.com", 
    "instagram.com", 
    "gmail.com", 
    "paypal.com", 
    "bank.com"
]

def check_domain_policy(url: str):
    """Raise ValueError if the URL domain matches the DENY_DOMAINS blocklist."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain and parsed.path:
            # Fallback path parsing for incomplete URIs
            domain = parsed.path.split("/")[0].lower()
            
        for deny in DENY_DOMAINS:
            if deny in domain:
                raise ValueError(f"Access to domain '{deny}' is blocked by SHAIL security policy.")
    except Exception as e:
        if "blocked by SHAIL security policy" in str(e):
            raise
        # Ignore parser errors, proceed with block verification default
        pass

class BrowserToolsAdapter:
    """
    Adapter bridging Phase 2 browser automation tools to WXT extension over WebSockets.
    """
    def __init__(self):
        self.name = "browser_tools"
        self.category = "browser"

    async def open_url(self, url: str) -> Dict[str, Any]:
        """Open a URL in a new browser tab. Gated by DENY domain list."""
        check_domain_policy(url)
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("open_url", url=url)

    async def read_page(self) -> Dict[str, Any]:
        """Read the visible innerText content of the active tab."""
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("read_page")

    async def click_element(self, selector: str) -> Dict[str, Any]:
        """Click a DOM element matching the query selector in the active tab."""
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("click_element", selector=selector)

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type text into a DOM input element matching the query selector in the active tab."""
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("type_text", selector=selector, text=text)

    async def scroll_page(self, direction: str = "down") -> Dict[str, Any]:
        """Scroll the active browser page page-up or page-down."""
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("scroll_page", direction=direction)

    async def wait_for_state(self, seconds: int = 5) -> Dict[str, Any]:
        """Wait for the active page DOM state or load triggers to complete."""
        from apps.shail.agent_api import send_browser_command
        return await send_browser_command("wait_for_state", seconds=seconds)

def register_browser_tools(provider):
    """
    Register browser automation tools with MCP provider.
    """
    adapter = BrowserToolsAdapter()
    
    @provider.register_tool
    async def browser_open_url(url: str) -> Dict[str, Any]:
        """Open a URL in a new tab. Gated by domain security policies."""
        return await adapter.open_url(url)
        
    @provider.register_tool
    async def browser_read_page() -> Dict[str, Any]:
        """Read the inner text of the active browser tab."""
        return await adapter.read_page()
        
    @provider.register_tool
    async def browser_click(selector: str) -> Dict[str, Any]:
        """Click an element on the active page matching the CSS selector."""
        return await adapter.click_element(selector)
        
    @provider.register_tool
    async def browser_type(selector: str, text: str) -> Dict[str, Any]:
        """Type text into an input matching the selector on the active page."""
        return await adapter.type_text(selector, text)
        
    @provider.register_tool
    async def browser_scroll(direction: str = "down") -> Dict[str, Any]:
        """Scroll the active page page-up or page-down."""
        return await adapter.scroll_page(direction)
        
    @provider.register_tool
    async def browser_wait(seconds: int = 5) -> Dict[str, Any]:
        """Wait for page load state or delay execution in seconds."""
        return await adapter.wait_for_state(seconds)
        
    provider.register_provider("browser_tools", adapter, category="browser")
    logger.info("Browser automation tools registered successfully with MCP provider")

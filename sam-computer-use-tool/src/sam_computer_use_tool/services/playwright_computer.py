"""Playwright-based implementation of the BaseComputer interface."""

import asyncio
import logging
from typing import List, Optional, Tuple, TYPE_CHECKING

from .base_computer import (
    BaseComputer,
    ComputerState,
    MouseButton,
    ScrollDirection,
)

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright
    from ..config import ComputerUseToolConfig

log = logging.getLogger(__name__)

# Pixels per scroll unit
SCROLL_PIXELS_PER_UNIT = 100
# Default wait after actions for page to settle
DEFAULT_ACTION_WAIT_MS = 100


class PlaywrightComputer(BaseComputer):
    """Playwright-based implementation of the BaseComputer interface.

    Provides browser automation using Playwright, supporting Chromium,
    Firefox, and WebKit browsers.
    """

    def __init__(self, config: "ComputerUseToolConfig"):
        """Initialize PlaywrightComputer.

        Args:
            config: Configuration object with viewport, browser, and other settings.
        """
        self._config = config
        self._playwright: Optional["Playwright"] = None
        self._browser: Optional["Browser"] = None
        self._context: Optional["BrowserContext"] = None
        self._page: Optional["Page"] = None
        self._viewport_width = config.viewport.width
        self._viewport_height = config.viewport.height

    @property
    def screen_size(self) -> Tuple[int, int]:
        """Return the viewport size as (width, height)."""
        return (self._viewport_width, self._viewport_height)

    def _denormalize_coords(self, x: float, y: float) -> Tuple[int, int]:
        """Convert normalized (0-1) coordinates to pixel coordinates if needed.

        Args:
            x: X coordinate (0.0-1.0 if normalized, pixels otherwise).
            y: Y coordinate (0.0-1.0 if normalized, pixels otherwise).

        Returns:
            Tuple of (pixel_x, pixel_y).
        """
        if self._config.normalize_coordinates:
            # Coordinates are in 0.0-1.0 range
            px_x = int(x * self._viewport_width)
            px_y = int(y * self._viewport_height)
            # Clamp to valid range
            px_x = max(0, min(px_x, self._viewport_width - 1))
            px_y = max(0, min(px_y, self._viewport_height - 1))
            return (px_x, px_y)
        # Already pixel coordinates
        return (int(x), int(y))

    async def start(self) -> None:
        """Initialize Playwright and launch browser."""
        from playwright.async_api import async_playwright

        log.info(
            "Starting PlaywrightComputer (headless=%s, browser=%s, viewport=%dx%d)",
            self._config.browser.headless,
            self._config.browser.browser_type,
            self._viewport_width,
            self._viewport_height,
        )

        self._playwright = await async_playwright().start()

        browser_types = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }
        browser_launcher = browser_types[self._config.browser.browser_type]

        self._browser = await browser_launcher.launch(
            headless=self._config.browser.headless,
            slow_mo=self._config.browser.slow_mo,
        )

        context_options = {
            "viewport": {
                "width": self._viewport_width,
                "height": self._viewport_height,
            }
        }
        if self._config.browser.user_agent:
            context_options["user_agent"] = self._config.browser.user_agent

        self._context = await self._browser.new_context(**context_options)
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self._config.browser.timeout_ms)

        log.info("PlaywrightComputer started successfully")

    async def close(self) -> None:
        """Close the browser and clean up resources."""
        log.info("Closing PlaywrightComputer...")

        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        log.info("PlaywrightComputer closed")

    def _ensure_page(self) -> "Page":
        """Ensure page is available, raise if not."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def navigate(self, url: str) -> None:
        """Navigate to a specific URL."""
        page = self._ensure_page()
        log.debug("Navigating to: %s", url)
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def click_at(
        self,
        x: float,
        y: float,
        button: MouseButton = MouseButton.LEFT,
        click_count: int = 1,
    ) -> None:
        """Click at the specified coordinates."""
        page = self._ensure_page()
        px_x, px_y = self._denormalize_coords(x, y)
        log.debug("Clicking at (%d, %d) button=%s count=%d", px_x, px_y, button, click_count)
        await page.mouse.click(
            px_x,
            px_y,
            button=button.value,
            click_count=click_count,
        )
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def hover_at(self, x: float, y: float) -> None:
        """Move mouse to hover at the specified coordinates."""
        page = self._ensure_page()
        px_x, px_y = self._denormalize_coords(x, y)
        log.debug("Hovering at (%d, %d)", px_x, px_y)
        await page.mouse.move(px_x, px_y)
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def type_text_at(
        self,
        x: float,
        y: float,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True,
    ) -> None:
        """Click at coordinates and type text."""
        page = self._ensure_page()
        px_x, px_y = self._denormalize_coords(x, y)
        log.debug(
            "Typing at (%d, %d): '%s' (enter=%s, clear=%s)",
            px_x,
            px_y,
            text[:50] + "..." if len(text) > 50 else text,
            press_enter,
            clear_before_typing,
        )

        # Click to focus
        await page.mouse.click(px_x, px_y)
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

        # Clear existing content if requested
        if clear_before_typing:
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")

        # Type the text
        await page.keyboard.type(text)

        # Press Enter if requested
        if press_enter:
            await page.keyboard.press("Enter")

        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def scroll_document(
        self,
        direction: ScrollDirection,
        amount: int = 3,
    ) -> None:
        """Scroll the entire document in the specified direction."""
        page = self._ensure_page()
        delta = amount * SCROLL_PIXELS_PER_UNIT
        log.debug("Scrolling document %s by %d pixels", direction, delta)

        if direction == ScrollDirection.UP:
            await page.mouse.wheel(0, -delta)
        elif direction == ScrollDirection.DOWN:
            await page.mouse.wheel(0, delta)
        elif direction == ScrollDirection.LEFT:
            await page.mouse.wheel(-delta, 0)
        elif direction == ScrollDirection.RIGHT:
            await page.mouse.wheel(delta, 0)

        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def scroll_at(
        self,
        x: float,
        y: float,
        direction: ScrollDirection,
        amount: int = 3,
    ) -> None:
        """Scroll at specific coordinates."""
        page = self._ensure_page()
        px_x, px_y = self._denormalize_coords(x, y)
        log.debug("Scrolling at (%d, %d) %s by %d units", px_x, px_y, direction, amount)

        # Move to position first
        await page.mouse.move(px_x, px_y)
        await self.scroll_document(direction, amount)

    async def wait(self, duration_ms: int) -> None:
        """Wait for specified milliseconds."""
        log.debug("Waiting for %d ms", duration_ms)
        await asyncio.sleep(duration_ms / 1000.0)

    async def go_back(self) -> None:
        """Navigate back in browser history."""
        page = self._ensure_page()
        log.debug("Going back in browser history")
        await page.go_back(wait_until="domcontentloaded")
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def go_forward(self) -> None:
        """Navigate forward in browser history."""
        page = self._ensure_page()
        log.debug("Going forward in browser history")
        await page.go_forward(wait_until="domcontentloaded")
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def search(self, query: str) -> None:
        """Navigate to Google and perform a search."""
        page = self._ensure_page()
        from urllib.parse import quote_plus

        search_url = f"https://www.google.com/search?q={quote_plus(query)}"
        log.debug("Searching for: %s", query)
        await page.goto(search_url, wait_until="domcontentloaded")
        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def key_combination(self, keys: List[str]) -> None:
        """Press a combination of keys."""
        page = self._ensure_page()
        log.debug("Pressing key combination: %s", keys)

        if len(keys) == 1:
            # Single key press
            await page.keyboard.press(keys[0])
        else:
            # Combination press (e.g., Ctrl+C)
            # Press all modifier keys, then the final key
            for key in keys[:-1]:
                await page.keyboard.down(key)
            await page.keyboard.press(keys[-1])
            for key in reversed(keys[:-1]):
                await page.keyboard.up(key)

        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def drag_and_drop(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        """Drag from start coordinates to end coordinates."""
        page = self._ensure_page()
        sx, sy = self._denormalize_coords(start_x, start_y)
        ex, ey = self._denormalize_coords(end_x, end_y)
        log.debug("Drag and drop from (%d, %d) to (%d, %d)", sx, sy, ex, ey)

        await page.mouse.move(sx, sy)
        await page.mouse.down()
        await page.mouse.move(ex, ey)
        await page.mouse.up()

        await asyncio.sleep(DEFAULT_ACTION_WAIT_MS / 1000)

    async def current_state(self) -> ComputerState:
        """Return the current state including a screenshot."""
        page = self._ensure_page()

        screenshot_options = {"type": self._config.screenshot_format}
        if self._config.screenshot_format == "jpeg":
            screenshot_options["quality"] = self._config.screenshot_quality

        screenshot_bytes = await page.screenshot(**screenshot_options)
        page_title = await page.title()

        return ComputerState(
            screenshot_bytes=screenshot_bytes,
            screenshot_mime_type=f"image/{self._config.screenshot_format}",
            current_url=page.url,
            page_title=page_title,
            viewport_size=(self._viewport_width, self._viewport_height),
        )

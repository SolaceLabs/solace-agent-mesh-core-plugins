"""Abstract base class for computer/browser control implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class MouseButton(str, Enum):
    """Mouse button enumeration."""

    LEFT = "left"
    MIDDLE = "middle"
    RIGHT = "right"


class ScrollDirection(str, Enum):
    """Scroll direction enumeration."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class ComputerState:
    """Represents the current state of the computer/browser.

    Attributes:
        screenshot_bytes: PNG/JPEG screenshot data as bytes.
        screenshot_mime_type: MIME type of the screenshot (image/png or image/jpeg).
        current_url: Current page URL (browser only).
        page_title: Current page title.
        viewport_size: Viewport dimensions as (width, height).
    """

    screenshot_bytes: bytes
    screenshot_mime_type: str
    current_url: Optional[str] = None
    page_title: Optional[str] = None
    viewport_size: Optional[Tuple[int, int]] = None


class BaseComputer(ABC):
    """Abstract base class for computer control implementations.

    Provides a common interface for browser automation that can be implemented
    by different backends (Playwright, Selenium, etc.).

    All coordinate parameters (x, y, end_x, end_y) accept normalized values
    between 0.0 and 1.0 when normalize_coordinates is True, or pixel values
    when False.
    """

    @property
    @abstractmethod
    def screen_size(self) -> Tuple[int, int]:
        """Return the screen/viewport size as (width, height) in pixels."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the browser.

        This method launches the browser process and creates a new page.
        Must be called before any other browser operations.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the browser and clean up all resources.

        After calling this method, the browser instance cannot be reused.
        """
        pass

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navigate to a specific URL.

        Args:
            url: The URL to navigate to (must include protocol, e.g., https://).
        """
        pass

    @abstractmethod
    async def click_at(
        self,
        x: float,
        y: float,
        button: MouseButton = MouseButton.LEFT,
        click_count: int = 1,
    ) -> None:
        """Click at the specified coordinates.

        Args:
            x: X coordinate (0.0-1.0 normalized or pixel value).
            y: Y coordinate (0.0-1.0 normalized or pixel value).
            button: Mouse button to use (left, middle, right).
            click_count: Number of clicks (1 for single, 2 for double).
        """
        pass

    @abstractmethod
    async def hover_at(self, x: float, y: float) -> None:
        """Move mouse to hover at the specified coordinates.

        Args:
            x: X coordinate (0.0-1.0 normalized or pixel value).
            y: Y coordinate (0.0-1.0 normalized or pixel value).
        """
        pass

    @abstractmethod
    async def type_text_at(
        self,
        x: float,
        y: float,
        text: str,
        press_enter: bool = False,
        clear_before_typing: bool = True,
    ) -> None:
        """Click at coordinates and type text.

        Args:
            x: X coordinate to click before typing.
            y: Y coordinate to click before typing.
            text: Text to type.
            press_enter: Whether to press Enter after typing.
            clear_before_typing: Whether to clear existing content first.
        """
        pass

    @abstractmethod
    async def scroll_document(
        self,
        direction: ScrollDirection,
        amount: int = 3,
    ) -> None:
        """Scroll the entire document in the specified direction.

        Args:
            direction: Direction to scroll (up, down, left, right).
            amount: Number of scroll units (each unit is ~100 pixels).
        """
        pass

    @abstractmethod
    async def scroll_at(
        self,
        x: float,
        y: float,
        direction: ScrollDirection,
        amount: int = 3,
    ) -> None:
        """Scroll at specific coordinates.

        Args:
            x: X coordinate to position mouse before scrolling.
            y: Y coordinate to position mouse before scrolling.
            direction: Direction to scroll.
            amount: Number of scroll units.
        """
        pass

    @abstractmethod
    async def wait(self, duration_ms: int) -> None:
        """Wait for specified milliseconds.

        Args:
            duration_ms: Time to wait in milliseconds.
        """
        pass

    @abstractmethod
    async def go_back(self) -> None:
        """Navigate back in browser history."""
        pass

    @abstractmethod
    async def go_forward(self) -> None:
        """Navigate forward in browser history."""
        pass

    @abstractmethod
    async def search(self, query: str) -> None:
        """Navigate to a search engine and perform a search.

        Args:
            query: Search query string.
        """
        pass

    @abstractmethod
    async def key_combination(self, keys: List[str]) -> None:
        """Press a combination of keys.

        Args:
            keys: List of key names to press together.
                  Examples: ["Control", "c"], ["Alt", "Tab"], ["Enter"]
        """
        pass

    @abstractmethod
    async def drag_and_drop(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        """Drag from start coordinates to end coordinates.

        Args:
            start_x: Starting X coordinate.
            start_y: Starting Y coordinate.
            end_x: Ending X coordinate.
            end_y: Ending Y coordinate.
        """
        pass

    @abstractmethod
    async def current_state(self) -> ComputerState:
        """Return the current state including a screenshot.

        Returns:
            ComputerState containing screenshot bytes, URL, title, and viewport size.
        """
        pass

"""ComputerUseTool - A DynamicTool for browser automation with artifact storage."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from google.adk.tools import ToolContext
from google.genai import types as adk_types
from pydantic import BaseModel

from solace_agent_mesh.agent.tools.dynamic_tool import DynamicTool
from solace_agent_mesh.agent.sac.component import SamAgentComponent
from solace_agent_mesh.agent.utils.artifact_helpers import save_artifact_with_metadata
from solace_agent_mesh.agent.utils.context_helpers import get_original_session_id

from .config import ComputerUseToolConfig
from .services.playwright_computer import PlaywrightComputer
from .services.base_computer import MouseButton, ScrollDirection

log = logging.getLogger(__name__)


class ComputerUseTool(DynamicTool):
    """A DynamicTool providing browser automation via Playwright.

    Screenshots are stored in SAM's artifact storage system, not returned inline.
    The browser is created on-demand via the open_browser action.
    """

    config_model = ComputerUseToolConfig

    def __init__(self, tool_config: ComputerUseToolConfig):
        super().__init__(tool_config)
        if isinstance(tool_config, dict):
            self.tool_config = ComputerUseToolConfig(**tool_config)
        else:
            self.tool_config = tool_config
        self._computer: Optional[PlaywrightComputer] = None

    @property
    def tool_name(self) -> str:
        return self.tool_config.tool_name

    @property
    def tool_description(self) -> str:
        base_desc = self.tool_config.tool_description
        if self._computer is not None:
            return f"{base_desc}\n\nBrowser Status: Open and ready"
        return f"{base_desc}\n\nBrowser Status: Not open. Call with action='open_browser' first."

    @property
    def parameters_schema(self) -> adk_types.Schema:
        """Define the tool's parameter schema for the LLM."""
        return adk_types.Schema(
            type=adk_types.Type.OBJECT,
            properties={
                "action": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description=(
                        "The action to perform. One of: "
                        "open_browser, close_browser, navigate, click, type, scroll, "
                        "hover, wait, go_back, go_forward, search, key_combination, "
                        "drag_and_drop, screenshot"
                    ),
                ),
                "url": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="URL to navigate to (for 'navigate' and optional for 'open_browser')",
                    nullable=True,
                ),
                "x": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="X coordinate (0.0-1.0 normalized, where 0=left, 1=right)",
                    nullable=True,
                ),
                "y": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="Y coordinate (0.0-1.0 normalized, where 0=top, 1=bottom)",
                    nullable=True,
                ),
                "text": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Text to type (for 'type' action)",
                    nullable=True,
                ),
                "button": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Mouse button: left, middle, right (default: left)",
                    nullable=True,
                ),
                "direction": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Scroll direction: up, down, left, right",
                    nullable=True,
                ),
                "amount": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Scroll amount in units (default: 3)",
                    nullable=True,
                ),
                "duration_ms": adk_types.Schema(
                    type=adk_types.Type.INTEGER,
                    description="Wait duration in milliseconds (for 'wait' action)",
                    nullable=True,
                ),
                "keys": adk_types.Schema(
                    type=adk_types.Type.ARRAY,
                    items=adk_types.Schema(type=adk_types.Type.STRING),
                    description="List of keys for key_combination (e.g., ['Control', 'c'])",
                    nullable=True,
                ),
                "query": adk_types.Schema(
                    type=adk_types.Type.STRING,
                    description="Search query (for 'search' action)",
                    nullable=True,
                ),
                "end_x": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="End X coordinate for drag_and_drop (0.0-1.0)",
                    nullable=True,
                ),
                "end_y": adk_types.Schema(
                    type=adk_types.Type.NUMBER,
                    description="End Y coordinate for drag_and_drop (0.0-1.0)",
                    nullable=True,
                ),
                "press_enter": adk_types.Schema(
                    type=adk_types.Type.BOOLEAN,
                    description="Press Enter after typing (default: false)",
                    nullable=True,
                ),
                "clear_before_typing": adk_types.Schema(
                    type=adk_types.Type.BOOLEAN,
                    description="Clear field before typing (default: true)",
                    nullable=True,
                ),
            },
            required=["action"],
        )

    async def init(self, component: SamAgentComponent, tool_config: Dict) -> None:
        """Initialize the tool (no browser startup - that's on-demand)."""
        log_id = f"[{self.tool_name}:init]"
        log.info("%s Tool initialized (browser will start on open_browser action)", log_id)

    async def cleanup(self, component: SamAgentComponent, tool_config: Dict) -> None:
        """Clean up resources - close browser if still open."""
        log_id = f"[{self.tool_name}:cleanup]"
        if self._computer:
            log.info("%s Closing browser during cleanup...", log_id)
            try:
                await self._computer.close()
            except Exception as e:
                log.warning("%s Error closing browser: %s", log_id, e)
            self._computer = None

    async def _generate_screenshot_name(
        self,
        action: str,
        page_title: Optional[str],
        url: Optional[str],
        tool_context: ToolContext,
    ) -> str:
        """Generate descriptive screenshot filename using LLM."""
        timestamp = datetime.now().strftime("%H%M%S")

        if not self.tool_config.use_llm_naming:
            # Simple naming without LLM
            return f"{self.tool_config.artifact_filename_prefix}_{action}_{timestamp}.png"

        # Build context for naming
        context_parts = [action]
        if page_title:
            context_parts.append(page_title[:30])
        if url:
            try:
                domain = urlparse(url).netloc.replace("www.", "")
                if domain:
                    context_parts.append(domain)
            except Exception:
                pass

        try:
            # Use LLM to generate concise descriptive name
            prompt = (
                f"Generate a short filename (3-5 words, snake_case, no extension) "
                f"for a browser screenshot of: {' - '.join(context_parts)}. "
                f"Respond with ONLY the filename, nothing else."
            )

            invocation_context = tool_context._invocation_context
            model = invocation_context.agent.model

            response = await model.generate_content_async(prompt)
            name = response.text.strip().lower()

            # Sanitize: keep only alphanumeric and underscores
            name = re.sub(r"[^a-z0-9_]", "_", name)
            name = re.sub(r"_+", "_", name).strip("_")
            name = name[:50]  # Limit length

            if name:
                return f"{name}_{timestamp}.png"
        except Exception as e:
            log.debug("LLM naming failed, using fallback: %s", e)

        # Fallback to simple naming
        return f"{self.tool_config.artifact_filename_prefix}_{action}_{timestamp}.png"

    async def _save_screenshot_artifact(
        self,
        tool_context: ToolContext,
        screenshot_bytes: bytes,
        mime_type: str,
        filename: str,
    ) -> Dict[str, Any]:
        """Save screenshot to SAM's artifact storage."""
        inv_context = tool_context._invocation_context
        artifact_service = inv_context.artifact_service

        if not artifact_service:
            return {"status": "error", "message": "ArtifactService not available"}

        try:
            save_result = await save_artifact_with_metadata(
                artifact_service=artifact_service,
                app_name=inv_context.app_name,
                user_id=inv_context.user_id,
                session_id=get_original_session_id(inv_context),
                filename=filename,
                content_bytes=screenshot_bytes,
                mime_type=mime_type,
                metadata_dict={
                    "description": "Browser screenshot from computer_use tool",
                    "source_tool": "sam_computer_use_tool",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                timestamp=datetime.now(timezone.utc),
            )
            return save_result
        except Exception as e:
            log.exception("Failed to save screenshot artifact: %s", e)
            return {"status": "error", "message": f"Failed to save screenshot: {e}"}

    async def _capture_and_save_state(
        self,
        action: str,
        tool_context: ToolContext,
    ) -> Dict[str, Any]:
        """Capture current state and save screenshot as artifact."""
        state = await self._computer.current_state()

        # Generate descriptive filename
        filename = await self._generate_screenshot_name(
            action=action,
            page_title=state.page_title,
            url=state.current_url,
            tool_context=tool_context,
        )

        # Save screenshot as artifact
        save_result = await self._save_screenshot_artifact(
            tool_context=tool_context,
            screenshot_bytes=state.screenshot_bytes,
            mime_type=state.screenshot_mime_type,
            filename=filename,
        )

        if save_result.get("status") == "error":
            return save_result

        return {
            "status": "success",
            "action": action,
            "current_url": state.current_url,
            "page_title": state.page_title,
            "viewport_size": state.viewport_size,
            "screenshot": {
                "filename": save_result.get("data_filename", filename),
                "version": save_result.get("data_version", 0),
                "mime_type": state.screenshot_mime_type,
            },
        }

    async def _run_async_impl(self, args: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Execute the requested browser action."""
        log_id = f"[{self.tool_name}:run]"
        tool_context = kwargs.get("tool_context")

        if not tool_context:
            return {"status": "error", "message": "ToolContext required"}

        action = args.get("action")
        if not action:
            return {"status": "error", "message": "action parameter is required"}

        log.info("%s Executing action: %s", log_id, action)

        try:
            # Handle open_browser action
            if action == "open_browser":
                if self._computer is not None:
                    return {"status": "error", "message": "Browser already open"}

                self._computer = PlaywrightComputer(self.tool_config)
                await self._computer.start()

                # Optionally navigate to URL
                if url := args.get("url"):
                    await self._computer.navigate(url)

                return await self._capture_and_save_state(action, tool_context)

            # Handle close_browser action
            elif action == "close_browser":
                if self._computer:
                    await self._computer.close()
                    self._computer = None
                return {"status": "success", "message": "Browser closed"}

            # All other actions require browser to be open
            if self._computer is None:
                return {
                    "status": "error",
                    "message": "Browser not open. Call with action='open_browser' first.",
                }

            # Execute the action
            if action == "navigate":
                url = args.get("url")
                if not url:
                    return {"status": "error", "message": "url required for navigate action"}
                await self._computer.navigate(url)

            elif action == "click":
                x, y = args.get("x"), args.get("y")
                if x is None or y is None:
                    return {"status": "error", "message": "x and y coordinates required for click"}
                button_str = args.get("button", "left")
                try:
                    button = MouseButton(button_str)
                except ValueError:
                    return {"status": "error", "message": f"Invalid button: {button_str}"}
                click_count = args.get("click_count", 1)
                await self._computer.click_at(x, y, button, click_count)

            elif action == "type":
                x, y = args.get("x"), args.get("y")
                text = args.get("text")
                if x is None or y is None or not text:
                    return {"status": "error", "message": "x, y, and text required for type"}
                press_enter = args.get("press_enter", False)
                clear_before = args.get("clear_before_typing", True)
                await self._computer.type_text_at(x, y, text, press_enter, clear_before)

            elif action == "scroll":
                direction_str = args.get("direction", "down")
                try:
                    direction = ScrollDirection(direction_str)
                except ValueError:
                    return {"status": "error", "message": f"Invalid direction: {direction_str}"}
                amount = args.get("amount", 3)
                x, y = args.get("x"), args.get("y")
                if x is not None and y is not None:
                    await self._computer.scroll_at(x, y, direction, amount)
                else:
                    await self._computer.scroll_document(direction, amount)

            elif action == "hover":
                x, y = args.get("x"), args.get("y")
                if x is None or y is None:
                    return {"status": "error", "message": "x and y required for hover"}
                await self._computer.hover_at(x, y)

            elif action == "wait":
                duration_ms = args.get("duration_ms", 1000)
                await self._computer.wait(duration_ms)

            elif action == "go_back":
                await self._computer.go_back()

            elif action == "go_forward":
                await self._computer.go_forward()

            elif action == "search":
                query = args.get("query")
                if not query:
                    return {"status": "error", "message": "query required for search"}
                await self._computer.search(query)

            elif action == "key_combination":
                keys = args.get("keys")
                if not keys or not isinstance(keys, list):
                    return {"status": "error", "message": "keys (list) required for key_combination"}
                await self._computer.key_combination(keys)

            elif action == "drag_and_drop":
                x, y = args.get("x"), args.get("y")
                end_x, end_y = args.get("end_x"), args.get("end_y")
                if any(v is None for v in [x, y, end_x, end_y]):
                    return {"status": "error", "message": "x, y, end_x, end_y required for drag_and_drop"}
                await self._computer.drag_and_drop(x, y, end_x, end_y)

            elif action == "screenshot":
                # Just capture current state without any action
                pass

            else:
                return {"status": "error", "message": f"Unknown action: {action}"}

            # Capture and save current state
            return await self._capture_and_save_state(action, tool_context)

        except Exception as e:
            log.exception("%s Error executing action '%s': %s", log_id, action, e)
            return {"status": "error", "message": str(e)}

import logging
from datetime import datetime, timezone
from fastmcp.server.middleware import Middleware, MiddlewareContext
from solace_agent_mesh.common.middleware.registry import MiddlewareRegistry
from solace_agent_mesh.gateway.adapter.base import GatewayAdapter

from .utils import validate_agent_access
from .mcp_adapter_config import McpAdapterConfig

log = logging.getLogger(__name__)


class ListingFilterMiddleware(Middleware):
    def __init__(self, adapter: GatewayAdapter):
        super().__init__()
        self.adapter = adapter

    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """
        Filter tools based on user permissions.

        This middleware intercepts list_tools calls and filters the result
        based on which agents the authenticated user has access to.
        """
        # Get the full tool list first
        result = await call_next(context)
        config: McpAdapterConfig = self.adapter.context.adapter_config

        # If auth is disabled or dev mode, return all tools
        if not config.enable_auth or config.dev_mode:
            log.debug("Auth disabled or dev mode - returning all tools")
            return result

        try:
            # Extract user identity from MCP context
            mcp_context = context.fastmcp_context
            user_id = None

            # Try to get user_id from the MCP context metadata
            # The auth handler should have populated this
            try:
                client_id = self.adapter._get_client_id(mcp_context)
                external_input = {
                    "tool_name": "None",
                    "agent_name": "None",
                    "skill_id": "None",
                    "message": "None",
                    "mcp_client_id": client_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                # Pass mcp_context through endpoint_context for per-request auth
                user_identity = await self.adapter.context.get_user_identity(
                    external_input,
                    endpoint_context={
                        "mcp_client_id": client_id,
                        "mcp_context": mcp_context
                    }
                )
                user_id = user_identity.get("id")
            except Exception as e:
                log.warning(f"Failed to get client_id from MCP context: {e}")

            # If still no user_id, use default (unauthenticated)
            if not user_id:
                log.warning("No user_id found in MCP context, using default identity")
                user_id = config.default_user_identity

            # Resolve user config using ConfigResolver
            config_resolver = MiddlewareRegistry.get_config_resolver()

            gateway_context = {
                "gateway_id": self.adapter.context.gateway_id,
                "gateway_app_config": self.adapter.context.config,
                "source": "mcp_list_tools",
            }

            user_config = await config_resolver.resolve_user_config(
                user_id, gateway_context, self.adapter.context.config
            )

            # Filter tools based on agent access permissions
            filtered_tools = []
            for tool in result:
                # Extract agent name from tool name
                # Tool names are in format: {agent_name}_{skill_name}
                tool_name = tool.name

                # Look up the agent for this tool
                if tool_name in self.adapter.tool_to_agent_map:
                    agent_name, _skill_id = self.adapter.tool_to_agent_map[tool_name]

                    if await validate_agent_access(agent_name, user_config):
                        filtered_tools.append(tool)

            log.info(
                "Filtered tools for user '%s': %d -> %d tools",
                user_id,
                len(result),
                len(filtered_tools),
            )

            return filtered_tools

        except Exception as e:
            # On error, log and return unfiltered list to avoid breaking clients
            log.error(
                "Error filtering tools by user permissions: %s. Returning unfiltered list.",
                e,
                exc_info=True,
            )
            return result

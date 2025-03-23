"""Manager for MCP server operations.

This module provides a manager class that handles MCP server operations,
including server initialization, tool registration, and request handling.
"""

import threading
import time
from typing import Dict, Any, Optional, List, Callable

from mcp.types import Tool, Resource, Prompt, PromptArgument, CallToolResult, TextContent, ReadResourceResult, GetPromptResult

from solace_ai_connector.common.log import log

from .mcp_server_factory import MCPServerFactory
from .agent_registry import AgentRegistry


class MCPServerManager:
    """Manager for MCP server operations.

    This class manages MCP server operations, including server initialization,
    tool registration, and request handling. It uses the agent registry to
    convert agent actions to MCP tools.

    Attributes:
        agent_registry: Registry of available agents.
        server_name: Name of the MCP server.
        host: Host address for the server (for SSE transport).
        port: Port for the server (for SSE transport).
        transport_type: Type of transport to use ('stdio' or 'sse').
        scopes: Scopes to filter agents by.
        server: The MCP server instance.
    """

    def __init__(
        self,
        agent_registry: AgentRegistry,
        server_name: str = "mcp-server",
        host: str = "0.0.0.0",
        port: int = 8080,
        transport_type: str = "stdio",
        scopes: str = "*:*:*",
        session_ttl_seconds: int = 3600,
    ):
        """Initialize the MCP server manager.

        Args:
            agent_registry: Registry of available agents.
            server_name: Name of the MCP server.
            host: Host address for the server (for SSE transport).
            port: Port for the server (for SSE transport).
            transport_type: Type of transport to use ('stdio' or 'sse').
            scopes: Scopes to filter agents by.
            session_ttl_seconds: Time-to-live for sessions in seconds.
        """
        self.agent_registry = agent_registry
        self.server_name = server_name
        self.host = host
        self.port = port
        self.transport_type = transport_type
        self.scopes = scopes
        self.server = None
        self.log_identifier = f"[MCPServerManager:{server_name}] "
        
        # Lock for thread-safe operations
        self.lock = threading.Lock()
        
        # Flag to track initialization
        self.initialized = False
        
        # Initialize session manager
        from .session_manager import SessionManager
        self.session_manager = SessionManager(session_ttl_seconds=session_ttl_seconds)
        
    def initialize(self) -> bool:
        """Initialize the MCP server.
        
        Returns:
            True if initialization was successful, False otherwise.
        """
        with self.lock:
            if self.initialized:
                return True
                
            try:
                # Get or create the server
                self.server = MCPServerFactory.get_server(
                    self.server_name,
                    self.host,
                    self.port,
                    self.transport_type
                )
                
                # Register tools from agent registry
                self._register_agent_tools()
                
                # Start the server
                self.server.start()
                
                self.initialized = True
                log.info(f"{self.log_identifier}Initialized MCP server")
                return True
            except Exception as e:
                log.error(
                    f"{self.log_identifier}Failed to initialize MCP server: {str(e)}",
                    exc_info=True
                )
                return False
                
    def shutdown(self) -> None:
        """Shut down the MCP server."""
        with self.lock:
            if not self.initialized:
                return
                
            MCPServerFactory.remove_server(self.server_name)
            self.server = None
            self.initialized = False
            log.info(f"{self.log_identifier}Shut down MCP server")
            
            # Clear all sessions
            if hasattr(self, 'session_manager'):
                for session_id in list(self.session_manager.sessions.keys()):
                    self.session_manager.remove_session(session_id)
            
    def _register_agent_tools(self) -> None:
        """Register agent actions as MCP tools."""
        if not self.server:
            return
            
        # Get filtered agents
        agents = self.agent_registry.get_filtered_agents(self.scopes)
        
        for agent_name, agent_data in agents.items():
            actions = agent_data.get("actions", [])
            
            for action in actions:
                if not action:
                    continue
                    
                action_name = action.get("name")
                if not action_name:
                    continue
                    
                # Skip actions without parameters or with invalid parameters
                params = action.get("params", [])
                if not isinstance(params, list):
                    log.warning(
                        f"{self.log_identifier}Skipping action {agent_name}.{action_name} "
                        f"with invalid params: {params}"
                    )
                    continue
                
                # Skip actions with no parameters defined
                if not params:
                    log.debug(
                        f"{self.log_identifier}Skipping action {agent_name}.{action_name} "
                        f"with no parameters defined"
                    )
                    continue
                
                # Create tool from action
                tool = self._create_tool_from_action(agent_name, action)
                
                # Create a closure to capture the current agent_name and action_name
                def create_handler(a_name, act_name):
                    return lambda args: self._handle_tool_call(a_name, act_name, args)
                
                # Register tool with server
                handler = create_handler(agent_name, action_name)
                self.server.register_tool(tool, handler)
                
                log.info(
                    f"{self.log_identifier}Registered tool {tool.name} "
                    f"for agent {agent_name}, action {action_name}"
                )
                
            # Register file resources for the agent if it has any
            self._register_agent_resources(agent_name, agent_data)
            
            # Register prompts for the agent if it has any
            self._register_agent_prompts(agent_name, agent_data)
                
    def _create_tool_from_action(self, agent_name: str, action: Dict[str, Any]) -> Tool:
        """Create an MCP tool from an agent action.
        
        Args:
            agent_name: Name of the agent.
            action: Action data.
            
        Returns:
            The MCP tool.
        """
        action_name = action.get("name")
        description = action.get("description", "")
        params = action.get("params", [])
        
        # Create input schema
        properties = {}
        required = []
        
        for param in params:
            param_name = param.get("name")
            if not param_name:
                continue
                
            param_desc = param.get("desc", "")
            param_type = param.get("type", "string")
            param_required = param.get("required", False)
            
            # Map agent mesh parameter types to JSON Schema types
            json_type = "string"  # Default type
            if param_type == "number" or param_type == "integer":
                json_type = param_type
            elif param_type == "boolean":
                json_type = "boolean"
            elif param_type == "array":
                json_type = "array"
                
            properties[param_name] = {
                "type": json_type,
                "description": param_desc
            }
            
            if param_required:
                required.append(param_name)
                
        input_schema = {
            "type": "object",
            "properties": properties,
            "required": required
        }
        
        # Create tool
        return Tool(
            name=f"{agent_name}.{action_name}",
            description=f"{description} (from agent {agent_name})",
            inputSchema=input_schema
        )
        
    def _handle_tool_call(
        self, agent_name: str, action_name: str, args: Dict[str, Any]
    ) -> CallToolResult:
        """Handle a tool call.
        
        Args:
            agent_name: Name of the agent.
            action_name: Name of the action.
            args: Arguments for the action.
            
        Returns:
            The tool call result.
        """
        try:
            # Validate agent exists
            agent = self.agent_registry.get_agent(agent_name)
            if not agent:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Agent '{agent_name}' not found")],
                    isError=True
                )
                
            # Validate action exists
            action = None
            for act in agent.get("actions", []):
                if act and act.get("name") == action_name:
                    action = act
                    break
                    
            if not action:
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Action '{action_name}' not found for agent '{agent_name}'")],
                    isError=True
                )
                
            # Validate parameters
            params = action.get("params", [])
            for param in params:
                param_name = param.get("name")
                param_required = param.get("required", False)
                
                if param_required and param_name not in args:
                    return CallToolResult(
                        content=[TextContent(type="text", text=f"Missing required parameter '{param_name}'")],
                        isError=True
                    )
            
            # Create and send action request to the agent
            import os
            import uuid
            import json
            from queue import Queue, Empty
            
            # Generate a correlation ID for tracking the request
            correlation_id = str(uuid.uuid4())
            
            # Create the action request
            action_request = {
                "agent_name": agent_name,
                "action_name": action_name,
                "action_params": args,
                "originator": "mcp_server_gateway",
                "action_idx": 0,  # Single action request
            }
            
            # Create a response queue for this request
            response_queue = Queue()
            
            # Store the correlation ID and response queue
            with self.lock:
                if not hasattr(self, 'pending_requests'):
                    self.pending_requests = {}
                self.pending_requests[correlation_id] = {
                    "queue": response_queue,
                    "timestamp": time.time(),
                    "agent_name": agent_name,
                    "action_name": action_name,
                }
            
            # Create the message to send
            topic = f"{os.getenv('SOLACE_AGENT_MESH_NAMESPACE', '')}solace-agent-mesh/v1/actionRequest/gateway/agent/{agent_name}/{action_name}"
            message = {
                "payload": action_request,
                "topic": topic,
                "user_properties": {
                    "mcp_correlation_id": correlation_id,
                    "gateway_id": self.server_name,
                }
            }
            
            # TODO: Send the message to the broker
            # This is a placeholder - in a real implementation, we would send the message to the broker
            log.info(f"{self.log_identifier}Sending action request to {agent_name}.{action_name} with correlation ID {correlation_id}")
            
            # Wait for the response with timeout
            timeout_seconds = 30  # Default timeout
            try:
                response = response_queue.get(timeout=timeout_seconds)
                
                # Process the response
                if isinstance(response, dict):
                    if "error" in response:
                        return CallToolResult(
                            content=[TextContent(type="text", text=f"Error: {response['error']}")],
                            isError=True
                        )
                    elif "message" in response:
                        return CallToolResult(
                            content=[TextContent(type="text", text=response["message"])]
                        )
                    else:
                        return CallToolResult(
                            content=[TextContent(type="text", text=str(response))]
                        )
                else:
                    return CallToolResult(
                        content=[TextContent(type="text", text=str(response))]
                    )
            except Empty:
                # Handle timeout
                with self.lock:
                    if correlation_id in self.pending_requests:
                        del self.pending_requests[correlation_id]
                
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Request to {agent_name}.{action_name} timed out after {timeout_seconds} seconds")],
                    isError=True
                )
            
            # For testing purposes, return a simulated response
            # In a real implementation, this would be replaced by the actual response handling
            result = f"Called {agent_name}.{action_name} with args: {args}"
            return CallToolResult(
                content=[TextContent(type="text", text=result)]
            )
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error calling {agent_name}.{action_name}: {str(e)}",
                exc_info=True
            )
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True
            )
            
    def _register_agent_resources(self, agent_name: str, agent_data: Dict[str, Any]) -> None:
        """Register agent resources as MCP resources.
        
        Args:
            agent_name: Name of the agent.
            agent_data: Agent data.
        """
        if not self.server:
            return
            
        # Check if agent has resources
        resources = agent_data.get("resources", [])
        if not resources:
            return
            
        for resource in resources:
            if not resource:
                continue
                
            resource_name = resource.get("name")
            resource_uri = resource.get("uri")
            resource_description = resource.get("description", "")
            resource_mime_type = resource.get("mime_type", "text/plain")
            
            if not resource_name or not resource_uri:
                continue
                
            # Create MCP resource
            mcp_resource = Resource(
                uri=f"agent://{agent_name}/{resource_uri}",
                name=resource_name,
                description=f"{resource_description} (from agent {agent_name})",
                mimeType=resource_mime_type
            )
            
            # Create a closure to capture the current agent_name and resource_uri
            def create_handler(a_name, r_uri):
                return lambda: self._handle_resource_read(a_name, r_uri)
                
            # Register resource with server
            handler = create_handler(agent_name, resource_uri)
            self.server.register_resource(mcp_resource, handler)
            
            log.info(
                f"{self.log_identifier}Registered resource {mcp_resource.uri} "
                f"for agent {agent_name}"
            )
            
    def _handle_resource_read(self, agent_name: str, resource_uri: str) -> ReadResourceResult:
        """Handle a resource read request.
        
        Args:
            agent_name: Name of the agent.
            resource_uri: URI of the resource.
            
        Returns:
            The resource read result.
        """
        try:
            # Validate agent exists
            agent = self.agent_registry.get_agent(agent_name)
            if not agent:
                return ReadResourceResult(
                    contents=[]
                )
                
            # Validate resource exists
            resource = None
            for res in agent.get("resources", []):
                if res and res.get("uri") == resource_uri:
                    resource = res
                    break
                    
            if not resource:
                return ReadResourceResult(
                    contents=[]
                )
                
            # TODO: Implement actual agent resource retrieval
            # This is a placeholder that will be implemented in Task 3.1
            content = f"Resource content for {agent_name}/{resource_uri}"
            mime_type = resource.get("mime_type", "text/plain")
            
            # Check if we're using the real MCP library or our mock
            try:
                # Try to use the real MCP library first
                from mcp.types import TextResourceContents as RealTextResourceContents
                
                # Create a dictionary that matches the expected structure
                resource_content = {
                    "uri": f"agent://{agent_name}/{resource_uri}",
                    "text": content,
                    "mimeType": mime_type
                }
                
                # Return the result with the content
                return ReadResourceResult(
                    contents=[resource_content]
                )
            except (ImportError, TypeError, ValueError):
                # If that fails, use our mock implementation
                from .mcp_server import TextResourceContents
                
                # Create a TextResourceContents object
                resource_content = TextResourceContents(
                    uri=f"agent://{agent_name}/{resource_uri}",
                    text=content,
                    mimeType=mime_type
                )
                
                # Return the result with the content
                return ReadResourceResult(
                    contents=[resource_content]
                )
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error reading resource {agent_name}/{resource_uri}: {str(e)}",
                exc_info=True
            )
            return ReadResourceResult(
                contents=[]
            )
            
    def _register_agent_prompts(self, agent_name: str, agent_data: Dict[str, Any]) -> None:
        """Register agent prompts as MCP prompts.
        
        Args:
            agent_name: Name of the agent.
            agent_data: Agent data.
        """
        if not self.server:
            return
            
        # Check if agent has prompts
        prompts = agent_data.get("prompts", [])
        if not prompts:
            return
            
        for prompt_data in prompts:
            if not prompt_data:
                continue
                
            prompt_name = prompt_data.get("name")
            prompt_description = prompt_data.get("description", "")
            prompt_arguments = prompt_data.get("arguments", [])
            
            if not prompt_name:
                continue
                
            # Convert prompt arguments to MCP format
            mcp_arguments = []
            for arg in prompt_arguments:
                if not arg:
                    continue
                    
                arg_name = arg.get("name")
                arg_description = arg.get("description", "")
                arg_required = arg.get("required", False)
                
                if not arg_name:
                    continue
                    
                mcp_arguments.append(
                    PromptArgument(
                        name=arg_name,
                        description=arg_description,
                        required=arg_required
                    )
                )
                
            # Create MCP prompt
            mcp_prompt = Prompt(
                name=f"{agent_name}.{prompt_name}",
                description=f"{prompt_description} (from agent {agent_name})",
                arguments=mcp_arguments
            )
            
            # Create a closure to capture the current agent_name and prompt_name
            def create_handler(a_name, p_name):
                return lambda args: self._handle_prompt_get(a_name, p_name, args)
                
            # Register prompt with server
            handler = create_handler(agent_name, prompt_name)
            self.server.register_prompt(mcp_prompt, handler)
            
            log.info(
                f"{self.log_identifier}Registered prompt {mcp_prompt.name} "
                f"for agent {agent_name}"
            )
            
    def update_agent_registry(self) -> None:
        """Update the server with the latest agent registry."""
        with self.lock:
            if not self.initialized:
                return
                
            # Re-register tools and resources
            self._register_agent_tools()
            
    def _handle_prompt_get(self, agent_name: str, prompt_name: str, args: Dict[str, Any]) -> GetPromptResult:
        """Handle a prompt get request.
        
        Args:
            agent_name: Name of the agent.
            prompt_name: Name of the prompt.
            args: Arguments for the prompt.
            
        Returns:
            The prompt get result.
        """
        try:
            # Validate agent exists
            agent = self.agent_registry.get_agent(agent_name)
            if not agent:
                return GetPromptResult(
                    messages=[]
                )
                
            # Validate prompt exists
            prompt = None
            for p in agent.get("prompts", []):
                if p and p.get("name") == prompt_name:
                    prompt = p
                    break
                    
            if not prompt:
                return GetPromptResult(
                    messages=[]
                )
                
            # Validate arguments
            prompt_arguments = prompt.get("arguments", [])
            for arg in prompt_arguments:
                arg_name = arg.get("name")
                arg_required = arg.get("required", False)
                
                if arg_required and arg_name not in args:
                    return GetPromptResult(
                        messages=[],
                        description=f"Missing required argument: {arg_name}"
                    )
                    
            # Get prompt template
            template = prompt.get("template", "")
            
            # Substitute arguments in template
            for arg_name, arg_value in args.items():
                template = template.replace(f"{{{arg_name}}}", str(arg_value))
                
            # Create prompt messages
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": template
                    }
                }
            ]
            
            # Return the result
            return GetPromptResult(
                messages=messages,
                description=prompt.get("description", "")
            )
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error getting prompt {agent_name}/{prompt_name}: {str(e)}",
                exc_info=True
            )
            return GetPromptResult(
                messages=[],
                description=f"Error: {str(e)}"
            )
            
    def handle_action_response(self, correlation_id: str, response_data: Dict[str, Any]) -> bool:
        """Handle an action response from an agent.
        
        Args:
            correlation_id: The correlation ID of the request.
            response_data: The response data from the agent.
            
        Returns:
            True if the response was handled, False otherwise.
        """
        with self.lock:
            if not hasattr(self, 'pending_requests'):
                return False
                
            if correlation_id not in self.pending_requests:
                log.warning(f"{self.log_identifier}Received response for unknown correlation ID: {correlation_id}")
                return False
                
            # Get the request info
            request_info = self.pending_requests[correlation_id]
            response_queue = request_info["queue"]
            
            # Put the response in the queue
            response_queue.put(response_data)
            
            # Remove the request from pending requests
            del self.pending_requests[correlation_id]
            
            return True
            
    def authenticate_client(self, client_id: str, credentials: Dict[str, Any]) -> Optional[str]:
        """Authenticate a client and create a session.
        
        Args:
            client_id: Identifier for the client.
            credentials: Authentication credentials.
            
        Returns:
            Session ID if authentication was successful, None otherwise.
        """
        try:
            session = self.session_manager.authenticate(client_id, credentials)
            if session:
                log.info(f"{self.log_identifier}Client {client_id} authenticated successfully")
                return session.session_id
            else:
                log.warning(f"{self.log_identifier}Authentication failed for client {client_id}")
                return None
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error authenticating client {client_id}: {str(e)}",
                exc_info=True
            )
            return None
            
    def authorize_request(self, session_id: str, scope: str) -> bool:
        """Check if a session is authorized for a specific scope.
        
        Args:
            session_id: The session ID to check.
            scope: The scope to check.
            
        Returns:
            True if the session is authorized, False otherwise.
        """
        try:
            authorized = self.session_manager.authorize(session_id, scope)
            if not authorized:
                log.warning(
                    f"{self.log_identifier}Session {session_id} not authorized for scope {scope}"
                )
            return authorized
        except Exception as e:
            log.error(
                f"{self.log_identifier}Error authorizing session {session_id} for scope {scope}: {str(e)}",
                exc_info=True
            )
            return False
            
    def get_session(self, session_id: str):
        """Get a session by ID.
        
        Args:
            session_id: The session ID to retrieve.
            
        Returns:
            The session if found, None otherwise.
        """
        return self.session_manager.get_session(session_id)
            
    def cleanup_pending_requests(self, max_age_seconds: int = 60) -> List[str]:
        """Clean up pending requests that have timed out.
        
        Args:
            max_age_seconds: Maximum age of requests in seconds.
            
        Returns:
            List of correlation IDs that were cleaned up.
        """
        cleaned_up = []
        current_time = time.time()
        
        with self.lock:
            if not hasattr(self, 'pending_requests'):
                return cleaned_up
                
            for correlation_id, request_info in list(self.pending_requests.items()):
                if current_time - request_info["timestamp"] > max_age_seconds:
                    # Request has timed out
                    response_queue = request_info["queue"]
                    agent_name = request_info["agent_name"]
                    action_name = request_info["action_name"]
                    
                    # Put a timeout error in the queue
                    response_queue.put({
                        "error": f"Request to {agent_name}.{action_name} timed out after {max_age_seconds} seconds"
                    })
                    
                    # Remove the request from pending requests
                    del self.pending_requests[correlation_id]
                    cleaned_up.append(correlation_id)
                    
                    log.warning(f"{self.log_identifier}Request to {agent_name}.{action_name} timed out after {max_age_seconds} seconds")
            
            # Also clean up expired sessions
            expired_sessions = self.session_manager.cleanup_expired_sessions()
            if expired_sessions:
                log.info(f"{self.log_identifier}Cleaned up {len(expired_sessions)} expired sessions")
            
            return cleaned_up

"""Action description"""
from solace_ai_connector.common.log import log

from solace_agent_mesh.common.action import Action
from solace_agent_mesh.common.action_response import ActionResponse
from solace_agent_mesh.services.file_service import FileService
import uuid
import os
import requests

class DrawAction(Action):
    def __init__(self, **kwargs):
        super().__init__(
            {
            "name": "draw",
            "prompt_directive": (
                "Draw a diagram or visualization using Mermaid.js syntax. It can"
                "process textual inputs to create flowcharts, sequence diagrams, "
                "Gantt charts, and other diagram types supported by Mermaid."
            ),
            "params": [
                {
                "name": "mermaid_code",
                "desc": "The input text using mermaid syntax to be rendered as a diagram.",
                "type": "string",
                }
            ],
            "required_scopes": ["mermaid:draw:create"],
            },
            **kwargs,
        )

    def invoke(self, params, meta={}) -> ActionResponse:
        log.debug("Invoking mermaid draw action for agent %s", self.parent_component.agent_name)
        session_id = meta.get("session_id")
        mermaid_code = params.get("mermaid_code")
        if not mermaid_code:
            return ActionResponse(message="Error: 'mermaid_code' parameter is required.", status_code=400)

        # Retrieve mermaid_server_url from the parent component's config
        mermaid_server_url = self.parent_component.get_config("mermaid_server_url")
        if not mermaid_server_url:
             log.error("Mermaid server URL not configured for agent %s", self.parent_component.agent_name)
             return ActionResponse(message="Error: Mermaid server URL is not configured.", status_code=500)

        return self.do_action(mermaid_code, mermaid_server_url, session_id)

    def do_action(self, mermaid_code, mermaid_server_url, session_id) -> ActionResponse:
        # Generate the diagram as PNG
        output_filename = f"{str(uuid.uuid4())[:6]}_diagram.png"
        mermaid_response = self._generate_mermaid_png(mermaid_code, mermaid_server_url, output_filename, session_id)

        # Check if error is raised when generating mermaid png
        if isinstance(mermaid_response, str):
            return ActionResponse(message=mermaid_response)

        return ActionResponse(files=[mermaid_response])

    def _generate_mermaid_png(self, mermaid_code, mermaid_server_url, output_file, session_id):
        """Generates PNG using the configured mermaid server."""
        try:
            # Do a POST to the mermaid server to get a PNG
            # Handle URLs with or without trailing slash
            base_url = mermaid_server_url.rstrip('/')
            request_url = f"{base_url}/generate?type=png"
            log.debug("Sending request to Mermaid server: %s", request_url)
            response = requests.post(request_url, data=mermaid_code, timeout=30) # Added timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        # Upload the PNG file to the file service
        file_service = FileService()
        image_meta = file_service.upload_from_buffer(
            response.content,
            file_name=output_file,
            session_id=session_id,
            data_source="Mermaid Agent - Draw Action",
        )
        return image_meta
    except Exception as e:
        log.error("Error generating Mermaid diagram: %s", str(e))
        return f"Error generating Mermaid diagram: {str(e)}"

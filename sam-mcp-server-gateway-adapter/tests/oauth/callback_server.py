"""
Lightweight HTTP server to receive OAuth callbacks.

This server listens on a local port and handles OAuth redirect callbacks
from the MCP server after user authorization.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from aiohttp import web

log = logging.getLogger(__name__)


class CallbackServer:
    """Lightweight HTTP server to receive OAuth callbacks."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        """
        Initialize callback server.

        Args:
            host: Host to bind to (default: 127.0.0.1)
            port: Port to bind to (default: 8888)
        """
        self.host = host
        self.port = port
        self.callback_future: Optional[asyncio.Future] = None
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None

    async def start(self) -> None:
        """Start the callback server."""
        self.app.router.add_get("/callback", self.handle_callback)
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, self.host, self.port)
        await self.site.start()
        log.info(f"Callback server started at http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the callback server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        log.info("Callback server stopped")

    async def handle_callback(self, request: web.Request) -> web.Response:
        """
        Handle OAuth callback and extract code/state.

        Args:
            request: aiohttp request object

        Returns:
            HTML response to display in browser
        """
        params = request.query
        code = params.get("code")
        state = params.get("state")
        error = params.get("error")
        error_description = params.get("error_description")

        result = {
            "code": code,
            "state": state,
            "error": error,
            "error_description": error_description,
        }

        log.info(f"Received OAuth callback: error={error}, has_code={bool(code)}")

        # Resolve the future if waiting
        if self.callback_future and not self.callback_future.done():
            self.callback_future.set_result(result)

        # Return HTML response to browser
        if error:
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>OAuth Error</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 3rem;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        max-width: 500px;
                        text-align: center;
                    }}
                    h1 {{
                        color: #e53e3e;
                        margin-bottom: 1rem;
                    }}
                    p {{
                        color: #4a5568;
                        line-height: 1.6;
                    }}
                    .error-code {{
                        background: #fed7d7;
                        color: #c53030;
                        padding: 0.5rem 1rem;
                        border-radius: 5px;
                        font-family: monospace;
                        margin-top: 1rem;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>❌ OAuth Error</h1>
                    <p><strong>Error:</strong> {error}</p>
                    <p>{error_description or 'An error occurred during authorization.'}</p>
                    <div class="error-code">Check the terminal for more details</div>
                    <p style="margin-top: 2rem; color: #718096;">You can close this window.</p>
                </div>
            </body>
            </html>
            """
        else:
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Authorization Successful</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    }}
                    .container {{
                        background: white;
                        padding: 3rem;
                        border-radius: 10px;
                        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                        max-width: 500px;
                        text-align: center;
                    }}
                    h1 {{
                        color: #38a169;
                        margin-bottom: 1rem;
                    }}
                    p {{
                        color: #4a5568;
                        line-height: 1.6;
                    }}
                    .success-icon {{
                        font-size: 4rem;
                        margin-bottom: 1rem;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="success-icon">✅</div>
                    <h1>Authorization Successful!</h1>
                    <p>Your OAuth authorization was successful.</p>
                    <p>The test client will continue automatically.</p>
                    <p style="margin-top: 2rem; color: #718096;">You can close this window.</p>
                </div>
            </body>
            </html>
            """

        return web.Response(text=html, content_type="text/html")

    async def wait_for_callback(self, timeout: int = 300) -> Dict[str, Any]:
        """
        Wait for OAuth callback with timeout.

        Args:
            timeout: Timeout in seconds (default: 300 = 5 minutes)

        Returns:
            Dictionary with callback data:
            - code: Authorization code (if successful)
            - state: State parameter
            - error: Error code (if error)
            - error_description: Error description (if error)

        Raises:
            asyncio.TimeoutError: If callback not received within timeout
        """
        self.callback_future = asyncio.Future()
        try:
            log.info(f"Waiting for OAuth callback (timeout: {timeout}s)...")
            result = await asyncio.wait_for(self.callback_future, timeout)
            return result
        except asyncio.TimeoutError:
            log.error(f"OAuth callback timeout after {timeout}s")
            return {
                "error": "timeout",
                "error_description": f"Callback not received within {timeout} seconds",
            }
        finally:
            self.callback_future = None

    @property
    def callback_uri(self) -> str:
        """Get the full callback URI."""
        return f"http://{self.host}:{self.port}/callback"

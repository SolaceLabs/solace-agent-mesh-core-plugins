import os
from abc import ABC
import base64
import logging
import time
import hashlib
import httpx
from typing import Any, Dict
from datetime import datetime, timezone
from urllib.parse import urlencode
import secrets

from starlette.responses import JSONResponse, RedirectResponse

from .mcp_adapter_config import McpAdapterConfig

log = logging.getLogger(__name__)

class McpAdapterAuthHandler(ABC):
    # Maps authorization code -> {tokens, created_at, code_challenge, redirect_uri}
    # Note: code_challenge is required when require_pkce is enabled (default)
    oauth_codes: Dict[str, Dict[str, Any]] = {}

    # OAuth state storage for authorize -> callback flow
    # Maps internal_state -> {client_redirect_uri, client_state, code_challenge, code_challenge_method, created_at, ttl_seconds}
    # Note: code_challenge and code_challenge_method are required when require_pkce is enabled (default)
    oauth_states: Dict[str, Dict[str, Any]] = {}


    def _get_base_url(self, config: McpAdapterConfig) -> str:
        """
        Get external base URL for OAuth endpoints.

        Uses MCP_EXTERNAL_BASE_URL environment variable if set (production),
        otherwise builds from host:port (local development).

        Returns:
            Base URL (e.g., "https://solacechatbeta.mymaas.net" or "http://0.0.0.0:8090")
        """
        external_base = os.environ.get("MCP_EXTERNAL_BASE_URL")
        if external_base:
            log.debug(f"Using external base URL from MCP_EXTERNAL_BASE_URL: {external_base}")
            return external_base.rstrip('/')  # Remove trailing slash if present

        # Fallback for local dev
        return f"http://{config.host}:{config.port}"

    def _register_oauth_endpoints(self) -> None:
        """
        Register OAuth endpoints with the FastMCP server.

        OAuth endpoints are added to the underlying Starlette app in _run_mcp_server().
        This method serves as documentation of the endpoints that will be exposed.

        OAuth endpoints that will be exposed:
        - GET /oauth/authorize - Initiates OAuth flow (via enterprise auth handler)
        - GET /oauth/callback - Handles OAuth callback (via enterprise auth handler)
        - GET /.well-known/oauth-authorization-server - OAuth metadata

        The actual OAuth logic is handled by the enterprise SAMOAuth2Handler,
        these routes just delegate to it.
        """
        if not self.context.auth_handler:
            return

        log.info(
            "OAuth endpoints will be added to HTTP server: "
            "/oauth/authorize, /oauth/callback, /.well-known/oauth-authorization-server"
        )

    async def _handle_oauth_authorize(self, request):
        """
        Handle GET /oauth/authorize

        Query params from MCP client:
            response_type: "code" (required)
            client_id: Client ID from registration
            redirect_uri: Client's callback URI (e.g., http://127.0.0.1:PORT/callback)
            scope: Requested scopes
            state: CSRF protection token
            code_challenge: PKCE challenge (required, RFC 7636)
            code_challenge_method: Must be "S256" (required)

        Returns:
            Redirect to WebUI OAuth proxy
        """
        config: McpAdapterConfig = self.context.adapter_config

        # Extract query parameters from MCP client
        query_params = dict(request.query_params)
        redirect_uri = query_params.get("redirect_uri")
        state = query_params.get("state")
        code_challenge = query_params.get("code_challenge")
        code_challenge_method = query_params.get("code_challenge_method")

        if not redirect_uri:
            return JSONResponse(
                {
                    "error": "invalid_request",
                    "error_description": "Missing redirect_uri",
                },
                status_code=400,
            )

        # Enforce PKCE requirement (RFC 7636)
        if config.require_pkce:
            if not code_challenge:
                log.error("MCP OAuth: code_challenge required but not provided")
                return JSONResponse({"error": "invalid_request"}, status_code=400)

            if not code_challenge_method:
                log.error("MCP OAuth: code_challenge_method required but not provided")
                return JSONResponse({"error": "invalid_request"}, status_code=400)

            if code_challenge_method != "S256":
                log.error(
                    "MCP OAuth: Unsupported code_challenge_method: %s",
                    code_challenge_method,
                )
                return JSONResponse({"error": "invalid_request"}, status_code=400)

        # Clean up expired OAuth states
        self._cleanup_expired_oauth_states()

        # Log successful PKCE validation
        if config.require_pkce:
            log.info(
                "MCP OAuth authorize: PKCE enforced, method=%s, redirect_uri=%s",
                code_challenge_method,
                redirect_uri,
            )

        # Store client's OAuth request in memory for callback
        # Generate internal state to correlate callback with this request
        internal_state = secrets.token_urlsafe(32)

        self.oauth_states[internal_state] = {
            "client_redirect_uri": redirect_uri,
            "client_state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "created_at": time.time(),
            "ttl_seconds": 300,  # 5 minutes
        }

        log.info("Stored OAuth state for internal_state=%s", internal_state)

        # Build MCP's callback URI (where OAuth2 service will send gateway code)
        base_url = self._get_base_url(config)
        mcp_callback_uri = f"{base_url}/oauth/callback"
        log.info("Using OAuth callback URI: %s", mcp_callback_uri)

        # Redirect to WebUI OAuth proxy with internal state
        proxy_params = {"gateway_uri": mcp_callback_uri, "state": internal_state, "provider": config.external_auth_provider}

        proxy_url = f"{config.external_auth_service_url}/login?{urlencode(proxy_params)}"

        log.info(
            "MCP OAuth: Redirecting to Auth server. Client redirect_uri=%s",
            redirect_uri,
        )

        return RedirectResponse(url=proxy_url, status_code=302)

    async def _handle_oauth_callback(self, request):
        """
        Handle GET /oauth/callback - OAuth callback from WebUI OAuth proxy.

        Query params from WebUI:
            code: Gateway code (single-use, short-lived)
            state: Internal state we sent in step 2

        Returns:
            Redirect to client's redirect_uri with authorization code
        """
        config: McpAdapterConfig = self.context.adapter_config

        # Extract gateway code and state from WebUI
        gateway_code = request.query_params.get("code")
        returned_state = request.query_params.get("state")

        if not gateway_code:
            log.error("MCP OAuth callback: Missing gateway code from WebUI")
            return JSONResponse(
                {
                    "error": "invalid_request",
                    "error_description": "Missing code parameter",
                },
                status_code=400,
            )

        # Look up OAuth state from in-memory storage
        state_data = self.oauth_states.get(returned_state)
        if not state_data:
            log.error(
                "MCP OAuth callback: Invalid or expired state parameter: %s",
                returned_state,
            )
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        # Check expiration
        age = time.time() - state_data["created_at"]
        if age > state_data["ttl_seconds"]:
            log.error("MCP OAuth callback: State expired (age=%.1fs)", age)
            del self.oauth_states[returned_state]
            return JSONResponse({"error": "invalid_request"}, status_code=400)

        # Get client's redirect info from stored state
        client_redirect_uri = state_data["client_redirect_uri"]
        client_state = state_data["client_state"]
        code_challenge = state_data["code_challenge"]
        code_challenge_method = state_data["code_challenge_method"]

        # Delete state (one-time use)
        del self.oauth_states[returned_state]

        log.info(
            "Retrieved OAuth state for internal_state=%s, client_redirect_uri=%s",
            returned_state,
            client_redirect_uri,
        )

        try:
            # Exchange gateway code for actual OAuth tokens from OAuth2 service
            # Must use same callback URI as in authorize step
            base_url = self._get_base_url(config)
            mcp_callback_uri = f"{base_url}/oauth/callback"

            async with httpx.AsyncClient(timeout=10.0) as client:
                params = urlencode({"code": gateway_code, "gateway_uri": mcp_callback_uri})
                exchange_response = await client.post(
                    f"{config.external_auth_service_url}/gateway-oauth/exchange?{params}",
                )

                if exchange_response.status_code != 200:
                    log.error(
                        "MCP OAuth: Gateway code exchange failed: %d %s",
                        exchange_response.status_code,
                        exchange_response.text,
                    )
                    return JSONResponse({"error": "server_error"}, status_code=502)

                tokens = exchange_response.json()
                access_token = tokens.get("access_token")
                refresh_token = tokens.get("refresh_token")

            if not access_token:
                log.error("MCP OAuth: No access token in exchange response")
                return JSONResponse({"error": "server_error"}, status_code=502)

            # Generate authorization code for MCP client
            # This code will be exchanged for tokens via /oauth/token endpoint
            authorization_code = secrets.token_urlsafe(32)

            # Store tokens associated with this authorization code (short-lived)
            self.oauth_codes[authorization_code] = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "created_at": time.time(),
                "code_challenge": code_challenge,
                "redirect_uri": client_redirect_uri,
                "ttl_seconds": 300,  # 5 minutes
            }

            # Build redirect to client with authorization code
            params = {"code": authorization_code}
            if client_state:
                params["state"] = client_state

            separator = "&" if "?" in client_redirect_uri else "?"
            redirect_url = f"{client_redirect_uri}{separator}{urlencode(params)}"

            log.info(
                "MCP OAuth: Successfully exchanged gateway code, redirecting to client at %s",
                client_redirect_uri,
            )

            return RedirectResponse(url=redirect_url, status_code=302)

        except httpx.RequestError as e:
            log.error(
                "MCP OAuth: Failed to connect to WebUI proxy for code exchange: %s", e
            )
            return JSONResponse({"error": "server_error"}, status_code=503)
        except Exception as e:
            log.error("MCP OAuth callback error: %s", e, exc_info=True)
            return JSONResponse({"error": "server_error"}, status_code=500)

    async def _handle_oauth_metadata(self, request):
        """
        Handle GET /.well-known/oauth-authorization-server - OAuth metadata.

        Returns RFC 8414 compliant OAuth 2.0 Authorization Server Metadata.

        IMPORTANT: This server REQUIRES PKCE (RFC 7636) for all authorization code grants
        when require_pkce is enabled (default). Clients must include code_challenge with method S256.
        """
        config: McpAdapterConfig = self.context.adapter_config
        base_url = self._get_base_url(config)
        metadata = {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}/oauth/authorize",
            "token_endpoint": f"{base_url}/oauth/token",
            "registration_endpoint": f"{base_url}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
                "none",
            ],
            "code_challenge_methods_supported": ["S256"],
        }

        # Add PKCE requirement indicator if enforced
        if config.require_pkce:
            metadata["require_pkce"] = True  # Non-standard but informative

        return JSONResponse(metadata)

    async def _handle_oauth_register(self, request):
        """
        Handle POST /oauth/register - Dynamic client registration (RFC 7591).

        For MCP gateways with pre-configured OAuth, we accept any registration
        and return a success response. The actual OAuth flow uses the gateway's
        pre-configured credentials with the OAuth2 service.

        NOTE: This server requires PKCE when require_pkce is enabled (default).
        """
        config: McpAdapterConfig = self.context.adapter_config

        try:
            # Parse the registration request (if provided)
            body = await request.json() if request.method == "POST" else {}

            # Generate client credentials (these are for Claude Code's records only,
            # the actual OAuth flow uses the gateway's pre-configured credentials)
            client_id = secrets.token_urlsafe(16)
            client_secret = secrets.token_urlsafe(32)

            # Return RFC 7591 compliant registration response
            response = {
                "client_id": client_id,
                "client_secret": client_secret,
                "client_id_issued_at": int(datetime.now(timezone.utc).timestamp()),
                "client_secret_expires_at": 0,  # Never expires
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",  # PKCE required, no client secret needed
            }

            # Add PKCE requirement indicator if enforced
            if config.require_pkce:
                response["require_pkce"] = True  # Inform client that PKCE is mandatory

            # Include any requested redirect URIs
            if "redirect_uris" in body:
                response["redirect_uris"] = body["redirect_uris"]

            log.info("Dynamic client registration: client_id=%s", client_id)
            return JSONResponse(response, status_code=201)

        except Exception as e:
            log.error("Client registration error: %s", e)
            return JSONResponse(
                {"error": "invalid_request", "error_description": str(e)},
                status_code=400,
            )

    async def _handle_oauth_token(self, request):
        """
        Handle POST /oauth/token - Token exchange endpoint.

        Request body (form-urlencoded):
            grant_type: "authorization_code" or "refresh_token"
            code: Authorization code (for authorization_code grant)
            redirect_uri: Must match the redirect_uri from /oauth/authorize
            code_verifier: PKCE code verifier (required when require_pkce is enabled, RFC 7636)
            refresh_token: Refresh token (for refresh_token grant)

        Returns:
            JSON with tokens:
            {
                "access_token": "...",
                "refresh_token": "...",
                "token_type": "Bearer",
                "expires_in": 3600
            }
        """

        try:
            # Get config early - needed for all grant types
            config: McpAdapterConfig = self.context.adapter_config

            # Cleanup expired codes before processing
            self._cleanup_expired_oauth_codes()

            # Parse form-urlencoded body
            body = await request.form()
            grant_type = body.get("grant_type")
            code = body.get("code")
            redirect_uri = body.get("redirect_uri")
            code_verifier = body.get("code_verifier")
            refresh_token = body.get("refresh_token")

            if grant_type == "authorization_code":
                # Validate required parameters
                if not code:
                    return JSONResponse({"error": "invalid_request"}, status_code=400)

                # Look up authorization code
                if not hasattr(self, "oauth_codes") or code not in self.oauth_codes:
                    log.warning(
                        "MCP OAuth token: Invalid or expired authorization code"
                    )
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)

                code_data = self.oauth_codes[code]

                # Check expiration
                age = time.time() - code_data["created_at"]
                if age > code_data["ttl_seconds"]:
                    log.warning(
                        "MCP OAuth token: Authorization code expired (age: %.1fs)", age
                    )
                    del self.oauth_codes[code]
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)

                # Validate redirect_uri matches
                if redirect_uri != code_data["redirect_uri"]:
                    log.error(
                        "MCP OAuth token: Redirect URI mismatch. Expected=%s, Got=%s",
                        code_data["redirect_uri"],
                        redirect_uri,
                    )
                    return JSONResponse({"error": "invalid_grant"}, status_code=400)

                # Validate PKCE (required when require_pkce is enabled)
                code_challenge = code_data.get("code_challenge")
                config: McpAdapterConfig = self.context.adapter_config

                if config.require_pkce:
                    # PKCE is mandatory
                    if not code_challenge:
                        log.error(
                            "MCP OAuth token: Authorization code missing code_challenge (config violation)"
                        )
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)

                    if not code_verifier:
                        log.error("MCP OAuth token: Missing code_verifier for PKCE")
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)

                    # Verify code_challenge = BASE64URL(SHA256(code_verifier))
                    verifier_hash = hashlib.sha256(
                        code_verifier.encode("ascii")
                    ).digest()
                    computed_challenge = (
                        base64.urlsafe_b64encode(verifier_hash)
                        .decode("ascii")
                        .rstrip("=")
                    )

                    if computed_challenge != code_challenge:
                        log.error("MCP OAuth token: PKCE verification failed")
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)

                    log.info("MCP OAuth token: PKCE verification successful")

                elif code_challenge:
                    # PKCE is optional but was used - validate it
                    if not code_verifier:
                        log.error("MCP OAuth token: Missing code_verifier for PKCE")
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)

                    # Verify code_challenge = BASE64URL(SHA256(code_verifier))
                    verifier_hash = hashlib.sha256(
                        code_verifier.encode("ascii")
                    ).digest()
                    computed_challenge = (
                        base64.urlsafe_b64encode(verifier_hash)
                        .decode("ascii")
                        .rstrip("=")
                    )

                    if computed_challenge != code_challenge:
                        log.error("MCP OAuth token: PKCE verification failed")
                        return JSONResponse({"error": "invalid_grant"}, status_code=400)

                    log.debug("MCP OAuth token: Optional PKCE verification successful")

                # Get tokens and delete code (one-time use)
                access_token = code_data["access_token"]
                refresh_token = code_data["refresh_token"]
                del self.oauth_codes[code]

                log.info(
                    "MCP OAuth: Successfully exchanged authorization code for tokens"
                )

                return JSONResponse(
                    {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_type": "Bearer",
                        "expires_in": 3600,  # 1 hour (this is just a hint, actual expiry managed by OAuth2 service)
                    }
                )

            elif grant_type == "refresh_token":
                # For refresh token grant, we need to call the OAuth2 service to get new tokens
                if not refresh_token:
                    log.warning("MCP OAuth token: Missing refresh_token parameter")
                    return JSONResponse(
                        {"error": "invalid_request", "error_description": "Missing refresh_token parameter"},
                        status_code=400,
                    )

                try:
                    # Exchange refresh token for new tokens via external auth service
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        refresh_response = await client.post(
                            f"{config.external_auth_service_url}/refresh_token",
                            json={
                                "refresh_token": refresh_token,
                                "provider": config.external_auth_provider
                            },
                        )

                        if refresh_response.status_code == 200:
                            new_tokens = refresh_response.json()
                            new_access_token = new_tokens.get("access_token")
                            new_refresh_token = new_tokens.get("refresh_token", refresh_token)  # Use old if not rotated

                            if not new_access_token:
                                log.error("MCP OAuth: No access token in refresh response")
                                return JSONResponse(
                                    {"error": "server_error"},
                                    status_code=500,
                                )

                            log.info("MCP OAuth: Successfully refreshed access token")

                            return JSONResponse(
                                {
                                    "access_token": new_access_token,
                                    "refresh_token": new_refresh_token,
                                    "token_type": "Bearer",
                                    "expires_in": new_tokens.get("expires_in", 3600),
                                }
                            )

                        elif refresh_response.status_code == 400:
                            # Invalid or expired refresh token
                            error_data = refresh_response.json() if refresh_response.headers.get("content-type", "").startswith("application/json") else {}
                            log.warning(
                                "MCP OAuth: Refresh token invalid or expired: %s",
                                error_data.get("error", "invalid_grant")
                            )
                            return JSONResponse(
                                {
                                    "error": error_data.get("error", "invalid_grant"),
                                    "error_description": error_data.get("error_description", "Refresh token is invalid or expired"),
                                },
                                status_code=400,
                            )

                        else:
                            log.error(
                                "MCP OAuth: Refresh token exchange failed: %d %s",
                                refresh_response.status_code,
                                refresh_response.text,
                            )
                            return JSONResponse(
                                {"error": "server_error"},
                                status_code=502,
                            )

                except httpx.RequestError as e:
                    log.error(
                        "MCP OAuth: Failed to connect to auth service for token refresh: %s", e
                    )
                    return JSONResponse(
                        {"error": "server_error", "error_description": "Failed to connect to authentication service"},
                        status_code=503,
                    )

            else:
                log.warning("MCP OAuth token: Unsupported grant_type: %s", grant_type)
                return JSONResponse(
                    {"error": "unsupported_grant_type"}, status_code=400
                )

        except Exception as e:
            log.error("MCP OAuth token error: %s", e, exc_info=True)
            return JSONResponse({"error": "server_error"}, status_code=500)

    def _cleanup_expired_oauth_codes(self) -> None:
        """
        Remove expired OAuth authorization codes to prevent memory leaks.
        Called periodically during token exchange.
        """
        import time

        try:
            now = time.time()
            expired = [
                code
                for code, data in self.oauth_codes.items()
                if now - data["created_at"] > data["ttl_seconds"]
            ]
            for code in expired:
                del self.oauth_codes[code]
            if expired:
                log.debug("Cleaned up %d expired OAuth codes", len(expired))
        except Exception as e:
            log.warning("Error during OAuth code cleanup: %s", e)

    def _cleanup_expired_oauth_states(self) -> None:
        """
        Remove expired OAuth states to prevent memory leaks.
        Called at the start of each authorize request.
        """
        import time

        try:
            now = time.time()
            expired = [
                state
                for state, data in self.oauth_states.items()
                if now - data["created_at"] > data["ttl_seconds"]
            ]
            for state in expired:
                del self.oauth_states[state]
            if expired:
                log.debug("Cleaned up %d expired OAuth states", len(expired))
        except Exception as e:
            log.warning("Error during OAuth state cleanup: %s", e)

    def auth_cleanup(self) -> None:
        """
        Cleanup resources used by the auth handler.
        """
        self.oauth_codes.clear()
        self.oauth_states.clear()
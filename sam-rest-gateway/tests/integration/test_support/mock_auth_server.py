"""
Mock Authentication Server for testing production authentication flows.
Simulates an external authentication service with token validation and user info endpoints.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class TokenValidationRequest(BaseModel):
    provider: str = "azure"

log = logging.getLogger(__name__)

class MockAuthServer:
    """
    Mock authentication server that implements the external auth service API.
    Provides endpoints for token validation and user information retrieval.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8090):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        
        self.app = FastAPI(title="Mock Auth Server", version="1.0.0")
        self.server: Optional[uvicorn.Server] = None
        self.server_thread: Optional[threading.Thread] = None
        self.started = False
        
        # Test data for authentication
        self.valid_tokens = {
            "valid_test_token_12345": {
                "email": "test_user@example.com",
                "name": "Test User",
                "roles": ["user"]
            },
            "admin_test_token_67890": {
                "email": "admin_user@example.com", 
                "name": "Admin User",
                "roles": ["admin", "user"]
            },
            "expired_test_token_abcde": None,  # Represents expired token
        }
        
        self.unauthorized_tokens = {
            "invalid_test_token_xyz",
            "malformed_token_123",
            "expired_test_token_abcde",
        }
        
        self._setup_routes()

    def _setup_routes(self):
        """Set up the authentication API routes."""
        
        @self.app.post("/is_token_valid")
        async def validate_token(
            request: Request,
            validation_request: TokenValidationRequest
        ):
            """
            Validates a Bearer token.
            Expected request: POST /is_token_valid
            Headers: Authorization: Bearer <token>
            Body: {"provider": "azure"}
            """
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Bearer token required"
                )
            
            token = auth_header[7:]  # Remove "Bearer " prefix

            log.debug("Mock Auth Server: Validating token: %s...", token[:10])

            if token in self.unauthorized_tokens:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            if token in self.valid_tokens and self.valid_tokens[token] is not None:
                log.debug("Mock Auth Server: Token validation successful for %s...", token[:10])
                return {"valid": True, "provider": validation_request.provider}

            log.debug("Mock Auth Server: Token validation failed for %s...", token[:10])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )

        @self.app.get("/user_info")
        async def get_user_info(request: Request, provider: str = "azure"):
            """
            Retrieves user information for a validated token.
            Expected request: GET /user_info?provider=azure
            Headers: Authorization: Bearer <token>
            """
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Bearer token required"
                )
            
            token = auth_header[7:]  # Remove "Bearer " prefix

            log.debug("Mock Auth Server: Getting user info for token: %s...", token[:10])

            if token in self.unauthorized_tokens:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            user_info = self.valid_tokens.get(token)
            if user_info is not None:
                log.debug("Mock Auth Server: User info retrieved for %s", user_info['email'])
                return {
                    "email": user_info["email"],
                    "name": user_info["name"],
                    "provider": provider,
                    "roles": user_info.get("roles", [])
                }

            log.debug("Mock Auth Server: User info not found for token %s...", token[:10])
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "service": "mock_auth_server"}

        @self.app.exception_handler(Exception)
        async def generic_exception_handler(request: Request, exc: Exception):
            """Handle unexpected exceptions."""
            log.exception("Mock Auth Server: Unhandled exception: %s", exc)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal server error"}
            )

    def start(self):
        """Start the mock authentication server in a background thread."""
        if self.started:
            log.warning("Mock Auth Server: Already started")
            return

        log.info("Mock Auth Server: Starting server on %s", self.url)

        config = uvicorn.Config(
            app=self.app,
            host=self.host,
            port=self.port,
            log_level="warning",  # Reduce uvicorn noise
            access_log=False,
        )
        self.server = uvicorn.Server(config)
        
        def _run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.server.serve())

        self.server_thread = threading.Thread(
            target=_run_server,
            daemon=True,
            name="MockAuthServer_Thread"
        )
        self.server_thread.start()
        
        # Wait for server to start
        max_retries = 20
        for i in range(max_retries):
            try:
                import httpx
                with httpx.Client() as client:
                    response = client.get(f"{self.url}/health", timeout=1.0)
                    if response.status_code == 200:
                        self.started = True
                        log.info("Mock Auth Server: Started successfully on %s", self.url)
                        return
            except Exception:
                pass
            time.sleep(0.1)
        
        raise RuntimeError(f"Mock Auth Server failed to start on {self.url}")

    def stop(self):
        """Stop the mock authentication server."""
        if not self.started:
            return
            
        log.info("Mock Auth Server: Stopping server...")
        if self.server:
            self.server.should_exit = True
            
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
            
        self.started = False
        log.info("Mock Auth Server: Stopped")

    def add_test_token(self, token: str, user_info: Dict[str, Any]):
        """Add a test token with associated user information."""
        self.valid_tokens[token] = user_info
        log.debug("Mock Auth Server: Added test token for %s", user_info.get('email', 'unknown'))

    def remove_test_token(self, token: str):
        """Remove a test token."""
        if token in self.valid_tokens:
            del self.valid_tokens[token]
            log.debug("Mock Auth Server: Removed test token %s...", token[:10])

    def clear_test_tokens(self):
        """Clear all test tokens except the default ones."""
        default_tokens = {
            "valid_test_token_12345",
            "admin_test_token_67890", 
            "expired_test_token_abcde"
        }
        
        tokens_to_remove = [
            token for token in self.valid_tokens.keys() 
            if token not in default_tokens
        ]
        
        for token in tokens_to_remove:
            del self.valid_tokens[token]
            
        log.debug("Mock Auth Server: Cleared custom test tokens")

    def get_test_tokens(self) -> Dict[str, str]:
        """Get a dictionary of test token names to actual tokens."""
        return {
            "valid": "valid_test_token_12345",
            "admin": "admin_test_token_67890",
            "invalid": "invalid_test_token_xyz",
            "expired": "expired_test_token_abcde",
            "malformed": "malformed_token_123",
        }

    def get_test_users(self) -> Dict[str, Dict[str, Any]]:
        """Get test user information."""
        return {
            "authorized": {
                "id": "test_user@example.com",
                "email": "test_user@example.com",
                "name": "Test User",
                "roles": ["user"]
            },
            "admin": {
                "id": "admin_user@example.com",
                "email": "admin_user@example.com", 
                "name": "Admin User",
                "roles": ["admin", "user"]
            },
            "unauthorized": {
                "id": "blocked_user@example.com",
                "email": "blocked_user@example.com",
                "name": "Blocked User",
                "roles": []
            }
        }

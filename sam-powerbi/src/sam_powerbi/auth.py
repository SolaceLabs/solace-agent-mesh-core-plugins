"""
PowerBI authentication for the sam-powerbi plugin.

Uses MSAL device-code flow (OAuth 2.0 RFC 8628) with a file-based token cache
for delegated (on-behalf-of-user) access to the PowerBI REST API.

The OAuth scope MUST be 'https://analysis.windows.net/powerbi/api/.default'.
Using any other scope will fail.

This module differs from the upstream brAIght implementation in two ways:
  1. Tenant/client IDs and the token cache path come from the constructor
     (populated from the SAM agent YAML tool_config), not module-level env
     vars — so a SAM install can run multiple PowerBI tools with different
     tenants if ever needed.
  2. The brAIght SSE status_callback is replaced with a `pending_holder`
     dict that the caller passes in. When the device-code flow starts, the
     flow details (verification_uri, user_code) are written to
     pending_holder['pending'] so the tool can return them synchronously
     to the LLM/user as an AUTH_REQUIRED result while the device-code poll
     runs in a background thread.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import msal

logger = logging.getLogger(__name__)

POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"


class PowerBIAuthError(RuntimeError):
    """Raised when the device-code flow ultimately fails (timeout, decline, etc.)."""


class PowerBIAuthPending(Exception):
    """
    Raised by get_token_or_start_device_flow when silent refresh is not
    possible and a device-code flow has just been initiated. The tool
    catches this, returns AUTH_REQUIRED to the user, and the background
    thread keeps polling until the user signs in (or the code expires).
    """

    def __init__(self, verification_uri: str, user_code: str, expires_in: int, message: str):
        self.verification_uri = verification_uri
        self.user_code = user_code
        self.expires_in = expires_in
        self.message = message
        super().__init__(message)


class PowerBIAuth:
    """
    Manages delegated PowerBI OAuth tokens via MSAL device-code flow.

    One instance per (tenant_id, client_id, token_cache_path) tuple. Safe
    for concurrent tool calls — all state transitions go through
    ``_token_lock``.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        token_cache_path: str = "/tmp/samv2/powerbi_msal_cache.json",
    ):
        if not tenant_id:
            raise ValueError("tenant_id is required for PowerBIAuth")
        if not client_id:
            raise ValueError("client_id is required for PowerBIAuth")

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._token_cache_path = token_cache_path
        self._authority = f"https://login.microsoftonline.com/{tenant_id}"

        self._token_lock = threading.Lock()
        # Tracks the in-flight device-code flow. When non-None, the background
        # thread is still polling. Subsequent get_token() calls return the
        # same pending info instead of starting a second flow.
        self._pending_flow: Optional[Dict[str, Any]] = None
        self._pending_thread: Optional[threading.Thread] = None

        self._cache = msal.SerializableTokenCache()
        if os.path.exists(token_cache_path):
            try:
                with open(token_cache_path) as f:
                    self._cache.deserialize(f.read())
                logger.info("[PowerBIAuth] Loaded token cache from %s", token_cache_path)
            except Exception as e:
                logger.warning("[PowerBIAuth] Failed to load cache: %s", e)

        self._app = msal.PublicClientApplication(
            client_id, authority=self._authority, token_cache=self._cache
        )

    # ── Cache helpers ──────────────────────────────────────────

    def _save_cache(self) -> None:
        if not self._cache.has_state_changed:
            return
        try:
            parent = os.path.dirname(self._token_cache_path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            with open(self._token_cache_path, "w") as f:
                f.write(self._cache.serialize())
            logger.debug("[PowerBIAuth] Cache saved to %s", self._token_cache_path)
        except Exception as e:
            logger.warning("[PowerBIAuth] Failed to save cache: %s", e)

    # ── Silent-refresh path ────────────────────────────────────

    def get_token_silent(self) -> Optional[str]:
        """Return a cached/refreshed token, or None if user interaction is needed."""
        accounts = self._app.get_accounts()
        if not accounts:
            return None
        result = self._app.acquire_token_silent([POWERBI_SCOPE], account=accounts[0])
        if result and "access_token" in result:
            self._save_cache()
            return result["access_token"]
        return None

    # ── Device-code flow (async) ───────────────────────────────

    def get_token_or_start_device_flow(self) -> str:
        """
        Return an access token if available silently. Otherwise, initiate a
        device-code flow in a background thread and raise ``PowerBIAuthPending``
        so the caller can surface the verification URL + user code immediately.

        If a device-code flow is already in-flight, the pending info for that
        flow is raised again — no second flow is started.

        Raises:
            PowerBIAuthPending: first call when user sign-in is needed.
            PowerBIAuthError:   flow failed (expired, declined, etc.).
        """
        with self._token_lock:
            # Fast path: silent refresh.
            token = self.get_token_silent()
            if token:
                return token

            # If a flow is already in-flight, just re-surface the pending info.
            if self._pending_flow is not None:
                pf = self._pending_flow
                raise PowerBIAuthPending(
                    verification_uri=pf["verification_uri"],
                    user_code=pf["user_code"],
                    expires_in=pf.get("expires_in", 900),
                    message=pf.get("message", ""),
                )

            # Start a new device-code flow.
            flow = self._app.initiate_device_flow(scopes=[POWERBI_SCOPE])
            if "user_code" not in flow:
                raise PowerBIAuthError(
                    f"Failed to start device-code flow: {json.dumps(flow)}"
                )

            self._pending_flow = {
                "flow": flow,
                "verification_uri": flow["verification_uri"],
                "user_code": flow["user_code"],
                "expires_in": int(flow.get("expires_in", 900)),
                "message": flow.get("message", ""),
            }
            logger.info(
                "[PowerBIAuth] Device-code flow started: %s at %s",
                flow["user_code"],
                flow["verification_uri"],
            )

            thread = threading.Thread(
                target=self._poll_device_flow,
                args=(flow,),
                daemon=True,
                name="powerbi-device-flow-poll",
            )
            self._pending_thread = thread
            thread.start()

            raise PowerBIAuthPending(
                verification_uri=flow["verification_uri"],
                user_code=flow["user_code"],
                expires_in=int(flow.get("expires_in", 900)),
                message=flow.get("message", ""),
            )

    def _poll_device_flow(self, flow: Dict[str, Any]) -> None:
        """Background poll loop. Clears _pending_flow on completion (success or failure)."""
        poll_interval = int(flow.get("interval", 5))
        expires_at = flow.get("expires_at") or (
            time.time() + int(flow.get("expires_in", 900))
        )
        result: Optional[Dict[str, Any]] = None
        poll_count = 0
        try:
            while time.time() < expires_at:
                result = self._app.acquire_token_by_device_flow(flow)
                poll_count += 1
                if "access_token" in result:
                    logger.info(
                        "[PowerBIAuth] Device-code flow succeeded after %d poll(s)",
                        poll_count,
                    )
                    break
                err = (result or {}).get("error", "")
                if err in ("authorization_pending", "slow_down"):
                    if err == "slow_down":
                        poll_interval += 5
                    time.sleep(poll_interval)
                    continue
                # Terminal error
                logger.warning("[PowerBIAuth] Device-code terminal error: %s", err)
                break

            if result and "access_token" in result:
                with self._token_lock:
                    self._save_cache()
            else:
                desc = (result or {}).get(
                    "error_description", (result or {}).get("error", "expired")
                )
                logger.warning("[PowerBIAuth] Device-code flow failed: %s", desc)
        finally:
            with self._token_lock:
                self._pending_flow = None
                self._pending_thread = None

    # ── Forced interactive (on 401) ────────────────────────────

    def force_reauth(self) -> None:
        """
        Invalidate the silent path (by clearing accounts from the cache) so
        the next get_token_or_start_device_flow call triggers a fresh
        device-code flow. Used on HTTP 401 responses.
        """
        with self._token_lock:
            for account in self._app.get_accounts():
                try:
                    self._app.remove_account(account)
                except Exception as e:
                    logger.warning("[PowerBIAuth] remove_account failed: %s", e)
            self._save_cache()

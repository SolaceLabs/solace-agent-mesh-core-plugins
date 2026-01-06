"""
PKCE (Proof Key for Code Exchange) utilities for OAuth 2.0.

Implements RFC 7636 compliant code verifier and challenge generation.
"""

import base64
import hashlib
import secrets
import string


class PKCEGenerator:
    """RFC 7636 compliant PKCE generator."""

    # RFC 7636 defines the code verifier character set
    VERIFIER_CHARS = string.ascii_letters + string.digits + "-._~"

    @staticmethod
    def generate_code_verifier(length: int = 128) -> str:
        """
        Generate cryptographically random code verifier.

        Per RFC 7636:
        - Must be 43-128 characters long
        - Must use [A-Z][a-z][0-9]-._~ character set
        - Should be cryptographically random

        Args:
            length: Length of verifier (43-128 characters, default 128)

        Returns:
            Code verifier string

        Raises:
            ValueError: If length is not between 43 and 128
        """
        if not 43 <= length <= 128:
            raise ValueError("Code verifier length must be between 43 and 128 characters")

        # Generate cryptographically random bytes and encode to base64url
        # We need more bytes than the target length to ensure we have enough after encoding
        random_bytes = secrets.token_bytes(96)
        verifier = base64.urlsafe_b64encode(random_bytes).decode("utf-8").rstrip("=")

        # Truncate to desired length
        return verifier[:length]

    @staticmethod
    def generate_code_challenge(verifier: str, method: str = "S256") -> str:
        """
        Generate code challenge from verifier.

        Per RFC 7636:
        - S256: code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
        - plain: code_challenge = code_verifier (not recommended)

        Args:
            verifier: Code verifier string
            method: Challenge method ('S256' or 'plain')

        Returns:
            Code challenge string

        Raises:
            ValueError: If method is not 'S256' or 'plain'
        """
        if method == "S256":
            # SHA256 hash of the verifier
            digest = hashlib.sha256(verifier.encode("ascii")).digest()
            # Base64 URL encode without padding
            challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
            return challenge
        elif method == "plain":
            # Plain method just returns the verifier
            return verifier
        else:
            raise ValueError(f"Unsupported code challenge method: {method}")

    @staticmethod
    def verify_challenge(verifier: str, challenge: str, method: str = "S256") -> bool:
        """
        Verify that verifier matches challenge.

        This is used for testing - the server does this verification.

        Args:
            verifier: Code verifier string
            challenge: Code challenge string to verify against
            method: Challenge method ('S256' or 'plain')

        Returns:
            True if verifier matches challenge, False otherwise
        """
        computed_challenge = PKCEGenerator.generate_code_challenge(verifier, method)
        return computed_challenge == challenge

    @staticmethod
    def generate_pkce_pair(length: int = 128, method: str = "S256") -> tuple[str, str]:
        """
        Generate a matched PKCE verifier and challenge pair.

        Convenience method that generates both verifier and challenge.

        Args:
            length: Length of verifier (43-128 characters)
            method: Challenge method ('S256' or 'plain')

        Returns:
            Tuple of (verifier, challenge)
        """
        verifier = PKCEGenerator.generate_code_verifier(length)
        challenge = PKCEGenerator.generate_code_challenge(verifier, method)
        return verifier, challenge

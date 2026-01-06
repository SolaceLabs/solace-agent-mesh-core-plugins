# OAuth Test Client

Interactive CLI tool to test OAuth endpoints and flows for the MCP Server Gateway Adapter.

## Features

- ✅ **Complete OAuth Flow Testing** - Full authorization code grant with PKCE
- 🔍 **Metadata Discovery** - RFC 8414 OAuth metadata endpoint validation
- 📝 **Client Registration** - RFC 7591 dynamic client registration
- 🔄 **Refresh Token Testing** - Identifies unimplemented refresh token grant
- 🔐 **PKCE Validation** - Tests PKCE enforcement and verification
- 📊 **Result Export** - JSON and Markdown report generation
- 🎨 **Beautiful CLI** - Rich terminal UI with colors and progress indicators

## Prerequisites

1. **MCP Server** running at `http://localhost:8090` (or custom URL)
2. **Auth Proxy** running at `http://localhost:8050` (or custom URL)
3. Python 3.10+

## Installation

Install test dependencies:

```bash
# From the project root
pip install -e ".[test]"
```

## Usage

### Interactive Mode

Run the interactive CLI menu:

```bash
cd tests/oauth
python oauth_test_client.py
```

This will display a menu where you can:
- Run individual tests
- Run all tests
- View previous results
- Export results to JSON/Markdown

### Command Line Mode

Run all tests:

```bash
python oauth_test_client.py --all
```

Run specific test:

```bash
python oauth_test_client.py --test complete-flow
python oauth_test_client.py --test metadata
python oauth_test_client.py --test registration
python oauth_test_client.py --test refresh
```

Export results:

```bash
python oauth_test_client.py --all --export json
python oauth_test_client.py --all --export markdown
python oauth_test_client.py --all --export both
```

Custom server URLs:

```bash
python oauth_test_client.py \
  --mcp-url http://localhost:8090 \
  --auth-url http://localhost:8050 \
  --callback-port 8888
```

Enable verbose logging:

```bash
python oauth_test_client.py --all --verbose
```

## Configuration

### Environment Variables

Create a `.env` file in the `tests/oauth/` directory:

```bash
# Server URLs
MCP_SERVER_URL=http://localhost:8090
AUTH_PROXY_URL=http://localhost:8050

# Callback server
CALLBACK_HOST=127.0.0.1
CALLBACK_PORT=8888

# Timeouts (seconds)
AUTHORIZATION_TIMEOUT=300

# Options
VERBOSE=true
AUTO_OPEN_BROWSER=true
RESULTS_DIR=./test_results

# Optional: Pre-registered client credentials
DEFAULT_CLIENT_ID=
DEFAULT_CLIENT_SECRET=
```

### Configuration File

The test client uses `config.py` which can load settings from environment variables or use defaults.

## Test Scenarios

### 1. OAuth Metadata Discovery

Tests the `/.well-known/oauth-authorization-server` endpoint.

**Validates**:
- RFC 8414 required fields (issuer, endpoints, grant types)
- PKCE support indicators
- Supported authentication methods

### 2. Dynamic Client Registration

Tests the `/oauth/register` endpoint.

**Validates**:
- RFC 7591 registration flow
- Client credentials generation
- Redirect URI handling

### 3. Complete OAuth Flow

Tests the full authorization code grant with PKCE.

**Steps**:
1. Register OAuth client (or use default)
2. Generate PKCE code_verifier and code_challenge
3. Start local callback server
4. Build authorization URL with PKCE parameters
5. Wait for user to authorize in browser
6. Receive authorization code via callback
7. Validate state parameter (CSRF protection)
8. Exchange code for tokens with PKCE verification
9. Validate token response

**Validates**:
- PKCE S256 method
- State parameter CSRF protection
- Authorization code flow
- Token exchange
- Access token and refresh token issuance

### 4. Refresh Token Flow

Tests the refresh token grant.

**Expected Result**: 400 `unsupported_grant_type` error (not implemented at adapter.py:857)

**Purpose**: Identifies the implementation gap for refresh tokens.

### 5. PKCE Validation Tests

Tests PKCE enforcement with:
- Invalid code_verifier (should fail)
- Missing code_verifier (should fail)
- Missing code_challenge (should fail)

**Validates**:
- Server correctly enforces PKCE
- Server validates SHA256 hash matching

## OAuth Flow Details

### Authorization Code Flow with PKCE

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  1. Client → Register (optional)                        │
│     POST /oauth/register                                │
│     ← client_id, client_secret                          │
│                                                         │
│  2. Generate PKCE                                       │
│     code_verifier = random(128 chars)                   │
│     code_challenge = BASE64URL(SHA256(code_verifier))   │
│                                                         │
│  3. Authorization Request                               │
│     GET /oauth/authorize?                               │
│       response_type=code&                               │
│       client_id=...&                                    │
│       redirect_uri=http://127.0.0.1:8888/callback&     │
│       code_challenge=...&                               │
│       code_challenge_method=S256&                       │
│       state=...                                         │
│                                                         │
│  4. User Authorization (browser)                        │
│     MCP → Auth Proxy → User login                       │
│     Auth Proxy → MCP callback                           │
│     MCP → Client callback with authorization code       │
│                                                         │
│  5. Token Exchange                                      │
│     POST /oauth/token                                   │
│       grant_type=authorization_code&                    │
│       code=...&                                         │
│       redirect_uri=http://127.0.0.1:8888/callback&     │
│       code_verifier=...                                 │
│     ← access_token, refresh_token                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Test Results

### Console Output

The test client displays:
- Real-time progress indicators
- Colored status (✓ PASS, ✗ FAIL, ℹ INFO)
- Detailed step-by-step results
- Summary statistics

### Exported Files

Results are exported to `./test_results/` directory:

**JSON Format** (`oauth_test_YYYYMMDD_HHMMSS.json`):
```json
{
  "timestamp": "2026-01-06T10:30:45Z",
  "config": { ... },
  "results": [ ... ],
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1
  }
}
```

**Markdown Format** (`oauth_test_YYYYMMDD_HHMMSS.md`):
- Human-readable test report
- Summary statistics
- Individual test details with steps
- Error messages

## Security Testing

The test client validates:

- ✅ PKCE enforcement (RFC 7636)
- ✅ State CSRF protection
- ✅ Authorization code expiration (5 min TTL)
- ✅ OAuth state expiration (5 min TTL)
- ✅ Code one-time use (replay protection)
- ✅ Redirect URI validation
- ✅ PKCE S256 verification (SHA256 hash matching)

## Known Limitations

1. **Refresh Token Grant**: Not implemented in the MCP adapter (adapter.py:857)
   - Test correctly identifies this gap
   - Returns 400 "unsupported_grant_type"

2. **Manual Authorization**: User must authorize in browser
   - Cannot be fully automated without mock auth server
   - Browser can auto-open if enabled

3. **State Expiration Test**: Requires waiting 5+ minutes
   - Not included in "Run All Tests" by default

## Troubleshooting

### Callback Server Port In Use

If port 8888 is already in use:

```bash
python oauth_test_client.py --callback-port 9999
```

### Connection Refused

Ensure MCP server and auth proxy are running:

```bash
# Check MCP server
curl http://localhost:8090/.well-known/oauth-authorization-server

# Check auth proxy
curl http://localhost:8050/health  # if health endpoint exists
```

### Browser Doesn't Open

Disable auto-open and manually visit the URL:

```bash
# In .env
AUTO_OPEN_BROWSER=false
```

### PKCE Verification Fails

Ensure the MCP server has PKCE enabled:

```yaml
# config.yaml
adapter_config:
  require_pkce: true
```

## Next Steps

After running tests and identifying the refresh token gap:

1. Review test results to confirm current implementation
2. Implement refresh token support at `adapter.py:857-860`
3. Re-run tests to validate implementation

## Contributing

To add new test scenarios:

1. Create a new class in `test_scenarios.py` inheriting from `TestScenario`
2. Implement the `run()` method returning `TestResult`
3. Add the test to `oauth_test_client.py` menu and CLI options

## License

Same as parent project.

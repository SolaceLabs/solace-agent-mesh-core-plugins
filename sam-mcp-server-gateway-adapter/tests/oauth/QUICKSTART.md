# Quick Start Guide

## Setup (First Time Only)

1. **Install dependencies**:
   ```bash
   cd /Users/cyrusmobini/Workspace/ai/solace-agent-mesh-core-plugins/sam-mcp-server-gateway-adapter
   pip install -e ".[test]"
   ```

2. **Verify servers are running**:
   ```bash
   # Check MCP server (should return OAuth metadata)
   curl http://localhost:8090/.well-known/oauth-authorization-server

   # Check auth proxy (should be accessible)
   curl http://localhost:8050
   ```

## Running Tests

### Option 1: Interactive Mode (Recommended)

```bash
cd tests
python -m oauth.oauth_test_client
```

Then select from the menu:
- `1` - Complete OAuth Flow (full end-to-end test)
- `2` - Metadata Discovery
- `3` - Client Registration
- `4` - Refresh Token (will show unimplemented)
- `a` - Run all tests
- `r` - View results
- `e` - Export results

### Option 2: Run All Tests

```bash
python oauth_test_client.py --all --export both
```

Results will be saved to `./test_results/`

### Option 3: Run Specific Test

```bash
# Test OAuth flow
python oauth_test_client.py --test complete-flow

# Test metadata
python oauth_test_client.py --test metadata

# Test refresh token (expect failure)
python oauth_test_client.py --test refresh
```

## What to Expect

### ✅ Tests That Should PASS

1. **Metadata Discovery** - OAuth metadata endpoint working
2. **Client Registration** - Dynamic client registration working
3. **Complete OAuth Flow** - Full authorization code grant with PKCE
   - You'll see a URL to open in your browser
   - After login, you'll be redirected back automatically
   - Tokens will be exchanged successfully

### ⚠️ Tests That Should EXPECTED_FAIL

4. **Refresh Token Flow** - Returns 400 "unsupported_grant_type"
   - This is expected - refresh tokens are not implemented yet
   - The test marks this as EXPECTED_FAIL (which means it passes)

## Understanding the Complete OAuth Flow Test

When you run the complete flow test:

1. **Client Registration** (automatic)
   - Test registers a new OAuth client
   - Receives client_id and client_secret

2. **PKCE Generation** (automatic)
   - Generates cryptographically random code_verifier
   - Computes SHA256 code_challenge

3. **Authorization URL** (manual step required)
   - Test displays a URL
   - **You must open this URL in your browser**
   - Browser auto-opens if AUTO_OPEN_BROWSER=true

4. **User Authorization** (in browser)
   - Browser redirects to auth proxy at localhost:8050
   - Complete the login process
   - Auth proxy redirects back to MCP server
   - MCP server redirects to test client callback

5. **Token Exchange** (automatic)
   - Test receives authorization code
   - Validates state parameter
   - Exchanges code for access_token with PKCE verification

## Troubleshooting

### "Connection refused" error

**Solution**: Make sure both servers are running:
```bash
# Terminal 1: Start MCP server
# (your command to start MCP server)

# Terminal 2: Start auth proxy
# (your command to start auth proxy)

# Terminal 3: Run tests
cd tests/oauth
python oauth_test_client.py
```

### "Callback timeout" error

**Solution**:
- Make sure you opened the authorization URL in your browser
- Complete the login within 5 minutes (300 seconds)
- If you need more time, set AUTHORIZATION_TIMEOUT=600 in .env

### Port 8888 already in use

**Solution**: Use a different callback port:
```bash
python oauth_test_client.py --callback-port 9999
```

### Browser doesn't open automatically

**Solution**: Disable auto-open and copy the URL manually:
```bash
# In .env
AUTO_OPEN_BROWSER=false
```

## Next Steps

After running tests:

1. **Review Results**
   - Check `./test_results/` for JSON and Markdown reports
   - Look for the refresh token test result (should be EXPECTED_FAIL)

2. **Implement Refresh Token Support**
   - Edit `src/sam_mcp_server_gateway_adapter/adapter.py` lines 854-860
   - Implement the missing refresh token grant type
   - Re-run tests to verify implementation

3. **Run Tests Again**
   ```bash
   python oauth_test_client.py --test refresh
   ```
   - After implementation, this should PASS instead of EXPECTED_FAIL

## Example Output

```
╭──────────────────────────────────────╮
│  MCP OAuth Test Client               │
│  Testing: http://localhost:8090      │
│  Auth Proxy: http://localhost:8050   │
╰──────────────────────────────────────╯

Available Tests:

  [1] Run Complete OAuth Flow
      Full authorization code grant with PKCE
  [2] Test OAuth Metadata Discovery
      RFC 8414 metadata endpoint
  [3] Test Dynamic Client Registration
      RFC 7591 client registration
  [4] Test Refresh Token Flow
      Expect failure - not implemented

  [a] Run All Tests
      Execute all test scenarios
  [r] View Test Results
      Display results from previous tests
  [e] Export Results
      Save results to JSON/Markdown
  [q] Quit
      Exit the test client

Select option:
```

## Questions?

See the full [README.md](README.md) for detailed documentation.

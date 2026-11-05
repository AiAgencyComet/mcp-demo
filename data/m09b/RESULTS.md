# Module 9b · caching hints + header gateway (measured 2026-11-05)
1. ttlMs (relist.json): a host that re-lists tools before every turn, 20 turns, through a logging proxy.
   Server default (no hint, ttlMs 0): 20 tools/list requests, 41 HTTP requests in all, 46.1 ms listing.
   `MCPServer(cache_hints={"tools/list": CacheHint(ttl_ms=300000, scope="public")})`: 1 tools/list request, 22 in all, 5.0 ms.
   The v2 `Client` honours ttlMs/cacheScope by default (`CacheConfig`); `share_public` is off by default and the SDK warns
   that a mislabelled "public" result leaks across tenants.
2. Prompt cache vs tool order (prompt_cache.json): 50 tools (11K tokens), cache_control on the last tool, 10 requests, Haiku 5.5.
   Stable order: 100,728 cache-read tokens, 11,192 written once, input cost $0.00249.
   Shuffled order each request: 0 cache reads, 111,920 written, $0.01408 (5.7x). No caching at all would be ~$0.0113,
   so shuffled + caching costs MORE than no caching (cache writes are 1.25x input). Deterministic tool lists matter.
3. Header gateway (gateway.txt, code/m09b/gateway.py, 21 lines; its docstring said "30-line" until 2026-11-05, fixed, code unchanged): rule "kiosk may not call refund".
   kiosk get_menu → HTTP 200; kiosk refund → HTTP 403 at the gateway; a request whose Mcp-Name header disagrees with the
   body (e.g. a client bug) → HTTP 400 from the server ("mcp-name header does not match the request body's 'name' parameter"),
   so a header-based rule cannot be skipped. Decision time on a 1 MB request: headers 0.04 µs vs body parse 714 µs.
   [Superseded 2026-11-05, see the Update below: "cannot be skipped" held only for new-spec requests, and the 1 MB number is withdrawn.]

## Update 2026-11-05 (review fix): gateway checks the protocol version first
The server also accepts old-spec requests, and the old path does not check Mcp-Name against the body. So the gateway now rejects
any request without `MCP-Protocol-Version: 2026-07-28` (spec: the intermediary "SHOULD reject the request rather than trusting
unvalidated header values"). `code/m09b/gateway.py` is now 25 lines (v1 kept as gateway_v1.py). gateway.txt (re-run):
get_menu 200 · refund 403 · header/body mismatch 400 · no version header 400 · version 2025-11-25 400.
Decision time for a typical 761 B request: headers 0.07 µs vs parsing the body 3 µs. Both are tiny; the old "1 MB, 16,000x"
number is withdrawn. The real gain: a proxy that does not speak JSON-RPC can decide from headers.

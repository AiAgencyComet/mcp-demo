Spec pages fetched 2026-11-05 with curl (the .md form of each page), for the module 3 rework (review/FIX_PLAN.md items 3, 4 and minor rows).
2026-07-28_streamable-http.md  https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http
2026-07-28_changelog.md        https://modelcontextprotocol.io/specification/2026-07-28/changelog
2025-11-25_transports.md       https://modelcontextprotocol.io/specification/2025-11-25/basic/transports

Quotes used on screen (verbatim):
- changelog, Major changes #4: "Replace the HTTP GET endpoint and `resources/subscribe`/`resources/unsubscribe` with
  `subscriptions/listen`: a single long-lived POST-response stream for opted-in server-to-client change notifications."   (m03-13)
- streamable-http, Protocol Version Header: "Every POST request to the MCP endpoint **MUST** include an `MCP-Protocol-Version` header."  (m03-08)
- streamable-http: "A server that supports clients implementing protocol versions earlier than `2025-06-18` ... **MAY** treat a request
  that omits the header as protocol version `2025-03-26`. A server that does not support such clients **MUST** reject a request without
  the header"   (m03-08)
- 2025-11-25 transports, Session Management 4: "When a client receives HTTP 404 in response to a request containing an `MCP-Session-Id`,
  it **MUST** start a new session by sending a new `InitializeRequest` without a session ID attached."   (m03-13)
- 2025-11-25 transports, Session Management 5: "Clients that no longer need a particular session (e.g., because the user is leaving the
  client application) **SHOULD** send an HTTP DELETE to the MCP endpoint with the `MCP-Session-Id` header, to explicitly terminate the session."  (m03-11/12)

Byte counts for "three required requests + an optional DELETE" (from data/m03/count.json "log"):
  initialize 240 sent / 544 received · notifications/initialized 218 / 155 · tools/call 278 / 470  -> 3 requests: 736 sent, 1,169 received, 1,905 total
  DELETE session 84 / 155 = 239                                                                 -> with the DELETE: 820 / 1,324 / 2,144 (count.json summary)
  new tools/call 462 / 404 = 866 (45.5% of 1,905; 40.4% of 2,144)

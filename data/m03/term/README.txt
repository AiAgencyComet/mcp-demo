Writer captures for script/m03.md (run 2026-11-05 05:47 UTC, mcp 2.3.0, server = code/m09/server_new.py on port 8391).
Suggested home: data/m03/term/<same file name>. Each file = full `curl -s -i` output (status line, headers, body).

H = -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream'
META3 = "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{},"io.modelcontextprotocol/clientInfo":{"name":"curl","version":"1"}}
META2 = the same without clientInfo

list_ok.txt          H + MCP-Protocol-Version + Mcp-Method: tools/list, params {META3}            -> 200, ttlMs 0, cacheScope private
list_nometa.txt      same, params {}                                                             -> 400, -32602 "params._meta must be an object carrying ..."
list_onlyinfo.txt    same, params {_meta: clientInfo only}                                       -> 400, -32602 "params._meta is missing the required envelope key(s): ..."
list_two_fields.txt  same, params {META2}                                                        -> 200 (clientInfo is optional)
call_ok.txt          Mcp-Method: tools/call, Mcp-Name: get_price, body name get_price, {META3}   -> 200, content + structuredContent
call_mismatch.txt    Mcp-Name: refund, body name get_price                                       -> 400, -32020 "mcp-name header does not match ..."
noname.txt           tools/call with no Mcp-Name header                                          -> 400, -32020 (same message)
nomethod.txt         tools/list with no Mcp-Method header                                        -> 400, -32020 "mcp-method header does not match the request body's method"
noversion.txt        tools/list with META2 but no MCP-Protocol-Version header                    -> 400, -32600 "Bad Request: Missing session ID" (server falls back to the old rules)
discover.txt         server/discover, params {}                                                  -> 400, -32602
discover_ok.txt      server/discover, params {META2}                                             -> 200, capabilities, supportedVersions ["2026-07-28"], ttlMs 0, cacheScope private
old_init.txt         no version header, method initialize, protocolVersion 2025-11-25            -> 200, text/event-stream, mcp-session-id header, protocolVersion 2025-11-25
raw_new_out.txt      code/m03/raw_new.py http://127.0.0.1:8391/mcp                              -> tools: ['get_price'] / result: {'result': '4.50 (answered by server pid 79770)'}

../m02_first_server_list.txt  SDK Client over stdio to code/m02/first_server.py: tools/list JSON + call get_price("mocha") (isError false)

# Module 9 · serverless model (local; no cloud)

Model: `code/m09s/funchost.py`: every HTTP request starts a FRESH server process ("cold start"), gets one response, and the process
stops. Nothing survives in memory between requests, as on a serverless platform. Runner: `code/m09s/run_serverless.py`.
One machine, one run per cell, 20 plain calls (`get_price`) or 12 refunds (two-round multi round-trip, `code/m07/two_rounds.py`).

| cell | spec / server | ok | HTTP requests | median per call | median cold start |
|---|---|---|---|---|---|
| warm_new_plain | new, ONE long-lived process (no function host) | 20/20 | – | 5 ms | – |
| new_plain | new (MCPServer) | 20/20 | 22 (discover, tools/list, 20 tools/call) | 568 ms | 322 ms |
| old_stateless_plain | old, `stateless_http=True` | 20/20 | 23 (initialize, initialized, tools/list, 20 calls) | 485 ms | 239 ms |
| old_stateful_plain | old, stateful default | 0/20 ("Session terminated") | 25 | – | 241 ms |
| old_stateful_reinit | old, stateful + client that re-initializes | 0/20 | 144 | – | 236 ms |
| mrtr_ephemeral | new, refund that asks back, key made per process | 0/12 ("Invalid or expired requestState") | 24 | – | 318 ms |
| mrtr_shared | new, refund that asks back, one key from the environment | 12/12 | 24 | – | 316 ms |

Readings:
- Plain calls work on serverless with the new spec AND with the old spec's stateless mode. The old stateful default cannot work:
  the session dies with its process after every request, and re-initializing only loops (144 requests, 0 answers).
- A cold start costs about 0.3 s per request here (Python start + SDK import); the new SDK starts slower than the old one
  (322 vs 239 ms). The new spec does not make cold starts cheaper; it makes them safe.
- Ask-back on serverless needs the shared key from the environment (a platform secret): 12/12 vs 0/12. The old spec's
  stateless mode cannot ask back at all (data/m09: 0/12 even on one copy).
- Not measured here, from module 7 and the spec: Tasks keep their state in a shared store, but the work stops when its copy
  stops (data/m07b fact 13), so on serverless long work needs a queue and a worker outside the function. `subscriptions/listen`
  is "a single long-lived POST-response stream", which a function with a time limit cannot hold open.

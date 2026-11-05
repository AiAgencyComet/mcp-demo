# Module 5 results (measured 2026-11-04/05, Claude API, all raw responses in raw_choice/ and raw_search/)

Setup: 10 made-up business servers x 20 tools = 200 tools (generated once by Sonnet 5.5, catalog.json, $0.54),
each with one natural request. Filter: keep a request only if Sonnet 5.5 picks its tool when it sees only that
server's 20 tools (173/200 kept; most drops were "look up first" behaviour, e.g. list_staff before create_shift).
CAVEAT for the script: the filter used Sonnet, so Sonnet's numbers start near 100% by construction; Haiku is the fair read.
CAVEAT 2: generated requests reuse the tool's words; real users are vaguer.
System prompt: "Do the request by calling exactly one tool. Do not ask questions." (Sonnet 5.5 rejects tool_choice
"any"/"tool": "tool_choice: type "tool" and "any" are not supported for this model.")
Score = first tool call is the labelled tool. Haiku: 173 requests; Sonnet: fixed sample of 50 (seed 7).

## Accuracy vs number of tools (good definitions)
| tools | Haiku 5.5 | Sonnet 5.5 (50) | avg input tokens |
|---|---|---|---|
| 5 | 91.3% | 100% | 1,426 |
| 10 | 92.5% | - | 2,478 |
| 20 | 91.3% | 98% | 4,628 |
| 50 | 91.3% | 98% | 10,945 |
| 100 | 89.6% | 100% | 21,563 |
| 200 | 88.4% | 98% | 42,788 |
Token cost of definitions alone (count_tokens): 1 tool 541, 5 = 1,327, 20 = 4,075, 50 = 11,260, 100 = 21,298, 200 = 42,709.
Latency Haiku 1,495 ms (5) -> 1,721 ms (200); Sonnet 2,329 -> 2,540 ms.

## What does Claude read? (50 tools)
| condition | Haiku | Sonnet | tokens |
|---|---|---|---|
| full | 91.3% | 98% | 10,945 |
| description "Tool." | 91.3% | 100% | 8,767 |
| opaque name (shop__t017) + description | 90.2% | 98% | 10,715 |
| opaque name + "Tool." | 89.6% | 98% | 8,537 |
| + schema descriptions removed (property names kept) | 90.2% | 98% | 7,867 |
| + properties renamed p1..pn (server prefix + enums kept) | 75.1% | 92% | 7,522 |
| void: name t073, "Tool.", only types/structure | 9.8% | 26% | 6,135 |
Lesson: one clear signal (name OR description OR property names) is enough; every part of the definition is read.

## Tool search, 200 tools all deferred (defer_loading: true)
| search | Haiku | Sonnet | avg input tokens | avg ms (Haiku / Sonnet) |
|---|---|---|---|---|
| none (all 200 loaded) | 88.4% | 98% | 42,788 | 1,721 / 2,540 |
| BM25 (tool_search_tool_bm25_20251119) | 90.2% | 98% | 2,686 / 2,803 | 2,481 / 4,012 |
| regex (tool_search_tool_regex_20251119) | 51.4% | 56% | 4,289 / 6,330 | 3,042 / 4,948 |
BM25: -94% input tokens, same accuracy, +0.8 s (Haiku) / +1.5 s (Sonnet). Regex fails because the model writes broad
OR patterns ("refund|payment", limit 10) and regex returns the first matches, not the best ones.
Haiku BM25 failures: 13/17 ended with no tool call after the search.

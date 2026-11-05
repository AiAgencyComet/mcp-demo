# Module 6b · the Fernhill agent among real servers (measured 2026-11-05, claude-haiku-5-5, 10 shop questions)
Tools offered: Fernhill (4, runs in-process) + the REAL tools/list of memory, filesystem, everything, playwright,
chrome-devtools, notion, github (171 tools, data/m06/tools_*.json; they never run: a call returns "This tool is not available here").

| mode | used Fernhill | calls to other servers | avg input tokens / question | avg time |
|---|---|---|---|---|
| all 175 loaded | 10/10 | 6 | 195,177 | 3,447 ms |
| all deferred + BM25 tool search | 7/10 | 2 | 7,172 | 3,480 ms |
| Fernhill loaded, other 171 deferred + BM25 | 9/10 | 0 | 3,584 | 2,453 ms |

Lessons (verbatim evidence in the jsonl files):
- "Read me our refund policy." fails in every mode: the policy is a RESOURCE (fernhill://policy/refunds); the model cannot open
  resources, the host does. With all tools loaded the model tried notion__API-post-search, filesystem__search_files,
  filesystem__list_allowed_directories, notion__API-get-self, chrome-devtools__list_pages, memory__search_nodes.
  Fix: expose it as a tool too, or let the host attach the resource.
- With everything deferred, the model did not know the shop existed: "How much is a double espresso?" → "A double espresso typically
  costs about $3 to $5 USD at a café in the US." Keep your own server loaded (Claude Code: _meta["anthropic/alwaysLoad"]) and defer the rest.
- Pinned + search: -98% input tokens and 29% faster than loading everything.

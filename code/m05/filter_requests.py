"""Keep only requests that Sonnet 5.5 maps to their own tool when it sees just that server's 20 tools."""
import json
from concurrent.futures import ThreadPoolExecutor
from common import CATALOG, DATA, choose, tool_def
def check(t):
    own = [tool_def(x) for x in CATALOG if x["server"] == t["server"]]
    r = choose("claude-sonnet-5-5", t["request"], own)
    return {"tool": t["full"], "pick": r["picks"][0] if r["picks"] else None}
with ThreadPoolExecutor(8) as ex: rows = list(ex.map(check, CATALOG))
keep = [r["tool"] for r in rows if r["pick"] == r["tool"]]
(DATA / "filter.json").write_text(json.dumps({"rows": rows, "keep": keep}, indent=1))
print("kept", len(keep), "of", len(rows))
for r in rows:
    if r["pick"] != r["tool"]: print("  drop:", r["tool"], "->", r["pick"])

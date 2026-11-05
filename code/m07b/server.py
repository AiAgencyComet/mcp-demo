"""Fernhill sales export as an MCP task (Tasks extension, spec 2026-07-28, mcp 2.3.0).
Usage: server.py PORT COPY_NAME shared|memory [DB_PATH]
  shared  task state in a sqlite file that every copy opens (the stateless way)
  memory  task state in this process only (to show what breaks behind a load balancer)
All data is invented. One "day" of the export takes FERNHILL_STEP_S seconds (default 1.0).
FERNHILL_POLL_MS sets the pollIntervalMs hint (default 2000)."""
import asyncio, os, random, sys, time
from datetime import date, timedelta
from pydantic import BaseModel, Field
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
import shop
from tasks_ext import MemoryTaskStore, SqliteTaskStore, TasksExtension, ask, progress

PORT, COPY, MODE = int(sys.argv[1]), sys.argv[2], sys.argv[3]
STEP_S = float(os.environ.get("FERNHILL_STEP_S", "1.0"))
POLL_MS = int(os.environ.get("FERNHILL_POLL_MS", "2000"))
TODAY = date(2026, 11, 4)
UNPRICED = {date(2026, 10, 12): ["A-0917", "A-0921"]}      # invented: two orders with no price, 24 days back

def log(msg: str) -> None:
    print(f"{time.time():.3f} copy {COPY} pid {os.getpid()}: {msg}", file=sys.stderr, flush=True)

def runs_as_task(tool: str, args: dict) -> bool:
    """Server-directed: the server decides per request. A report of more than 5 days runs as a task."""
    return tool == "export_sales_report" and int(args.get("days", 0)) > 5

store = SqliteTaskStore(sys.argv[4]) if MODE == "shared" else MemoryTaskStore()
tasks = TasksExtension(store, runs_as_task, ttl_ms=3_600_000, poll_interval_ms=POLL_MS, log=log)
mcp = MCPServer("fernhill", instructions="Fernhill Coffee sales tools.", extensions=[tasks])

class SalesReport(BaseModel):
    first_day: str
    last_day: str
    days: int
    orders: int
    revenue: float = Field(description="US dollars")
    top_drink: str
    skipped_orders: list[str]

def day_sales(d: date) -> list[str]:
    rng = random.Random(d.toordinal())                    # the same invented sales on every run
    return rng.choices(list(shop.MENU), weights=[3, 6, 2, 3, 2], k=rng.randint(38, 72))

@mcp.tool()
async def export_sales_report(days: int) -> SalesReport:
    """Build the Fernhill sales report for the last `days` days (1 to 90). A long report runs as a task."""
    if not 1 <= days <= 90:
        raise ToolError(f"days must be 1 to 90, not {days}.")
    orders, revenue, counts, skipped = 0, 0.0, {}, []
    for i in range(days):
        d = TODAY - timedelta(days=i)
        await progress(f"Day {i + 1} of {days}: reading {d.isoformat()} ({round(100 * i / days)}% done)")
        if d in UNPRICED:
            answer = await ask(f"unpriced-{d.isoformat()}",
                               f"{len(UNPRICED[d])} orders on {d.isoformat()} have no price ({', '.join(UNPRICED[d])}). Skip them?",
                               {"type": "object", "properties": {"skip": {"type": "boolean"}}, "required": ["skip"]})
            if not (answer.get("action") == "accept" and answer.get("content", {}).get("skip")):
                raise ToolError(f"Export stopped on {d.isoformat()}: {len(UNPRICED[d])} orders have no price.")
            skipped += UNPRICED[d]
        await asyncio.sleep(STEP_S)                         # the slow part (a real shop: a database or an API)
        for drink in day_sales(d):
            orders, revenue = orders + 1, revenue + shop.MENU[drink]["price"]
            counts[drink] = counts.get(drink, 0) + 1
    return SalesReport(first_day=(TODAY - timedelta(days=days - 1)).isoformat(), last_day=TODAY.isoformat(), days=days,
                       orders=orders, revenue=round(revenue, 2), top_drink=max(counts, key=counts.get), skipped_orders=skipped)

if __name__ == "__main__":
    log(f"start, store={MODE}")
    mcp.run(transport="streamable-http", port=PORT)

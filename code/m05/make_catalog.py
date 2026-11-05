"""Build a realistic tool catalog: 10 made-up servers x 20 tools, each tool with one natural request that needs it.
Generated once with Claude Sonnet 5.5, saved to data/m05/catalog.json (raw responses in data/m05/raw_catalog/)."""
import json, logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import anthropic
from dotenv import load_dotenv
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "data" / "m05"; RAW = DATA / "raw_catalog"; RAW.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / "code" / ".env"); api = anthropic.Anthropic()
SERVERS = {
 "shop": "the Fernhill Coffee shop: menu, orders, refunds, loyalty points, pickup times",
 "suppliers": "buying beans, milk and cups from suppliers: purchase orders, deliveries, invoices from suppliers",
 "payments": "card payments, payouts, chargebacks, payment refunds, fees",
 "staff": "staff rota, shifts, time off, wages, staff training",
 "crm": "customer records, customer notes, customer complaints, segments, emails to customers",
 "calendar": "calendar events, meetings, rooms, reminders",
 "email": "sending, reading, searching and labelling email in the shop mailbox",
 "accounting": "ledger, expenses, tax, profit and loss, budgets",
 "inventory": "stock levels in the shop, stock counts, waste, low-stock alerts",
 "marketing": "social posts, promotions, discount codes, campaign results",
}
PROMPT = """Design the tools of an MCP server for {desc}. Name the server "{name}".
Return JSON only: {{"tools": [ ... 20 items ... ]}}. Each item:
{{"name": snake_case tool name (no server prefix), "description": one or two sentences, what it does and when to use it,
 "input_schema": a JSON Schema object with properties and required, "request": one realistic sentence that a shop
 manager would type to an AI assistant, which needs THIS tool and no other tool of this server}}.
Make the tools realistic and specific. Some tools of this server should sound close to tools of other business
servers (for example a refund, an order, a customer, a report), because real deployments look like that."""

def build(name):
    r = api.messages.create(model="claude-sonnet-5-5", max_tokens=16000,
                            messages=[{"role": "user", "content": PROMPT.format(name=name, desc=SERVERS[name])}])
    (RAW / f"{name}.json").write_text(r.model_dump_json(indent=1))
    text = "".join(b.text for b in r.content if b.type == "text")
    text = text[text.find("{"): text.rfind("}") + 1]
    tools = json.loads(text)["tools"]
    for t in tools: t["server"] = name
    return tools, r.usage

with ThreadPoolExecutor(5) as ex:
    res = list(ex.map(build, SERVERS))
catalog = [t for tools, _ in res for t in tools]
cost = sum(u.input_tokens * 2 + u.output_tokens * 10 for _, u in res) / 1e6
(DATA / "catalog.json").write_text(json.dumps(catalog, indent=1))
print(len(catalog), "tools;", f"cost ${cost:.3f}")
for t in catalog[:3] + catalog[100:102]: print(t["server"], t["name"], "|", t["request"])

import asyncio, json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "fernhill"))
import server as fernhill
from agent import run
q = "I want a large oat latte for pickup, name Sam. What is the total, and what is my order ID?"
log = []
m = asyncio.run(run(q, {"fernhill": fernhill.mcp}, log=log))
out = __import__("pathlib").Path(__file__).resolve().parents[2] / "data/m04/try_agent.json"
out.write_text(json.dumps({"question": q, "metrics": m, "raw": log}, indent=1))
print(json.dumps({k: v for k, v in m.items() if k != "answer"}, indent=1)); print("ANSWER:", m["answer"])

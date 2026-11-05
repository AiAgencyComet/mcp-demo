"""The context tax of all eight servers in ONE tool list (added 2026-11-05 after review).
context_tax.py counts each server alone, so each of its eight counts includes the fixed tool-use preamble once.
This script counts the eight saved lists (data/m06/tools_<server>.json) together, with the same question, in the same way.
Usage:  ../.venv-new/bin/python combined_tax.py  -> data/m06/tax_combined.json"""
import json
from pathlib import Path
import anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "data" / "m06"
load_dotenv(ROOT / "code" / ".env"); api = anthropic.Anthropic()
Q = [{"role": "user", "content": "What does a large latte cost?"}]
ORDER = ["fernhill", "memory", "filesystem", "everything", "playwright", "chrome-devtools", "notion", "github"]

tax = json.loads((DATA / "tax.json").read_text())
defs = [d for s in ORDER for d in json.loads((DATA / f"tools_{s}.json").read_text())]
out = {"tools": len(defs), "models": {}}
for m in ("claude-haiku-5-5", "claude-sonnet-5-5"):
    q = api.messages.count_tokens(model=m, messages=Q).input_tokens
    together = api.messages.count_tokens(model=m, messages=Q, tools=defs).input_tokens - q
    one = api.messages.count_tokens(model=m, messages=Q, tools=defs[:1]).input_tokens - q
    summed = sum(tax["servers"][s][m] for s in ORDER)
    out["models"][m] = {"question_tokens": q, "sum_of_eight_counts": summed, "one_list_together": together,
                        "difference": summed - together, "first_tool_alone": one}
    print(m, out["models"][m])
(DATA / "tax_combined.json").write_text(json.dumps(out, indent=1))

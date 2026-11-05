import json, logging, random, time
from pathlib import Path
import anthropic
from dotenv import load_dotenv
logging.disable(logging.INFO)
ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "data" / "m05"
load_dotenv(ROOT / "code" / ".env"); api = anthropic.Anthropic(max_retries=6)
CATALOG = json.loads((DATA / "catalog.json").read_text())
for t in CATALOG: t["full"] = f"{t['server']}__{t['name']}"
BY = {t["full"]: t for t in CATALOG}
PRICE = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0)}

OPAQUE = {t["full"]: f"{t['server']}__t{i:03d}" for i, t in enumerate(CATALOG)}
VOID = {t["full"]: f"t{(i * 73) % 200:03d}" for i, t in enumerate(CATALOG)}  # no server prefix, order scrambled

def void_schema(x):
    """Keep only structure: types and property count. Remove enums, formats, patterns and limits too."""
    if isinstance(x, dict):
        return {k: void_schema(v) for k, v in x.items() if k not in ("enum", "const", "format", "pattern", "minimum", "maximum",
                "minLength", "maxLength", "minItems", "maxItems", "exclusiveMinimum", "exclusiveMaximum", "multipleOf")}
    if isinstance(x, list): return [void_schema(v) for v in x]
    return x

def strip_docs(x):
    """Remove every description, title and example from a JSON Schema; keep property names and types."""
    if isinstance(x, dict):
        return {k: strip_docs(v) for k, v in x.items() if k not in ("description", "title", "examples", "example", "default")}
    if isinstance(x, list): return [strip_docs(v) for v in x]
    return x

def blind(x):
    """Also rename every property to p1, p2, ... (and keep the required list consistent)."""
    if isinstance(x, dict):
        x = dict(x)
        if isinstance(x.get("properties"), dict):
            names = list(x["properties"]); ren = {n: f"p{i+1}" for i, n in enumerate(names)}
            x["properties"] = {ren[n]: blind(v) for n, v in x["properties"].items()}
            if isinstance(x.get("required"), list): x["required"] = [ren.get(n, n) for n in x["required"]]
        return {k: (blind(v) if k != "properties" else v) for k, v in x.items()}
    if isinstance(x, list): return [blind(v) for v in x]
    return x

def tool_def(t, vague=False, opaque=False, schema="full"):
    sch = t["input_schema"]
    if schema in ("bare", "blind"): sch = strip_docs(sch)
    if schema in ("blind", "void"): sch = blind(strip_docs(sch))
    if schema == "void":
        return {"name": VOID[t["full"]], "description": "Tool.", "input_schema": void_schema(sch)}
    return {"name": OPAQUE[t["full"]] if opaque else t["full"],
            "description": ("Tool." if vague else t["description"]), "input_schema": sch}

SYSTEM = "You are the assistant of a coffee shop manager. Do the request by calling exactly one tool. Do not ask questions."

def choose(model, request, tools, extra=None, tool_choice={"type": "auto"}, **kw):
    t0 = time.perf_counter()
    r = api.messages.create(model=model, max_tokens=600, tools=tools + (extra or []), tool_choice=tool_choice,
                            system=SYSTEM, messages=[{"role": "user", "content": request}], **kw)
    ms = (time.perf_counter() - t0) * 1000
    picks = [b.name for b in r.content if b.type == "tool_use"]
    return {"picks": picks, "input_tokens": r.usage.input_tokens, "output_tokens": r.usage.output_tokens, "ms": ms,
            "raw": r.model_dump(mode="json")}

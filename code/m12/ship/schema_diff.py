"""Compare two tools/list snapshots and say which version bump the change needs.
  python schema_diff.py old.json new.json --old-version 1.1.0 --new-version 1.2.0
Exit 1 when the new version number is smaller than the change needs (for example a breaking change in a minor bump).

Rules (for the model AND for any client that calls the tools):
  MAJOR  tool removed or renamed | new required input | input removed | input type changed | enum value removed
         | output field removed or its type changed
  MINOR  tool added | optional input added | enum value added | output field added
  EVAL   description changed: no contract change, but the model's choice can change -> run the eval (module 12)
         and, for clients that pin descriptions, it looks like a rug pull (module 11)."""
import json, sys
from pathlib import Path

RANK = {"none": 0, "eval": 0, "patch": 1, "minor": 2, "major": 3}


def resolve(schema, node):
    if isinstance(node, dict) and "$ref" in node:
        return schema.get("$defs", {}).get(node["$ref"].split("/")[-1], {})
    return node

def walk_props(schema, node=None, path=""):
    """Yield (path, property_schema, required?) for every property, through $ref, anyOf and array items."""
    node = schema if node is None else resolve(schema, node)
    req = set(node.get("required", []))
    for name, p in (node.get("properties") or {}).items():
        here = f"{path}.{name}" if path else name
        yield here, p, name in req
        p = resolve(schema, p)
        for alt in p.get("anyOf", []):
            alt = resolve(schema, alt)
            yield from walk_props(schema, alt, f"{here}<{alt.get('title', '?')}>")
        if "properties" in p:
            yield from walk_props(schema, p, here)
        if p.get("type") == "array":
            yield from walk_props(schema, p.get("items", {}), here + "[]")

def kind(schema, p):
    p = resolve(schema, p)
    return p.get("type") or ("anyOf" if "anyOf" in p else "const" if "const" in p else "?")

def descriptions(schema):
    return {path: resolve(schema, p).get("description") for path, p, _ in walk_props(schema)}


def diff(old, new):
    out = []
    o, n = {t["name"]: t for t in old}, {t["name"]: t for t in new}
    for name in o.keys() - n.keys(): out.append(("major", f"tool removed: {name}"))
    for name in n.keys() - o.keys(): out.append(("minor", f"tool added: {name}"))
    for name in o.keys() & n.keys():
        a, b = o[name], n[name]
        for side, sa, sb in (("input", a.get("inputSchema", {}), b.get("inputSchema", {})),
                             ("output", a.get("outputSchema", {}), b.get("outputSchema", {}))):
            pa = {path: (p, r) for path, p, r in walk_props(sa)}
            pb = {path: (p, r) for path, p, r in walk_props(sb)}
            for path in pa.keys() - pb.keys():
                out.append(("major", f"{name}: {side} '{path}' removed" + (" (old callers' value is now silently ignored)" if side == "input" else "")))
            for path in pb.keys() - pa.keys():
                if side == "input":
                    out.append(("major", f"{name}: new required input '{path}'") if pb[path][1] else ("minor", f"{name}: optional input '{path}' added"))
                else:
                    out.append(("minor", f"{name}: output '{path}' added"))
            for path in pa.keys() & pb.keys():
                (x, xr), (y, yr) = pa[path], pb[path]
                if kind(sa, x) != kind(sb, y): out.append(("major", f"{name}: {side} '{path}' type {kind(sa, x)} -> {kind(sb, y)}"))
                if side == "input" and yr and not xr: out.append(("major", f"{name}: input '{path}' is now required"))
                ea, eb = set(resolve(sa, x).get("enum", [])), set(resolve(sb, y).get("enum", []))
                if ea - eb: out.append(("major" if side == "input" else "minor", f"{name}: {side} '{path}' enum lost {sorted(ea - eb)}"))
                if eb - ea: out.append(("minor" if side == "input" else "major", f"{name}: {side} '{path}' enum gained {sorted(eb - ea)}"))
        if a.get("description") != b.get("description"):
            out.append(("eval", f"{name}: description changed  {a.get('description')!r} -> {b.get('description')!r}"))
        da, db = descriptions(a.get("inputSchema", {})), descriptions(b.get("inputSchema", {}))
        for path in da.keys() & db.keys():
            if da[path] != db[path]:
                out.append(("eval", f"{name}: input '{path}' description changed  {da[path]!r} -> {db[path]!r}"))
    return out


def bump(old_v, new_v):
    """Which part of the version moved. 2.0.0-rc1 counts as major."""
    a = [int(x) for x in old_v.split("-")[0].split(".")]; b = [int(x) for x in new_v.split("-")[0].split(".")]
    return "major" if b[0] > a[0] else "minor" if b[1] > a[1] else "patch" if b[2] > a[2] else "none"


def main(argv):
    old, new = json.loads(Path(argv[1]).read_text()), json.loads(Path(argv[2]).read_text())
    ov, nv = argv[argv.index("--old-version") + 1], argv[argv.index("--new-version") + 1]
    changes = diff(old, new)
    order = {"major": 0, "minor": 1, "eval": 2}
    for level, text in sorted(changes, key=lambda c: (order[c[0]], c[1])):
        print(f"  {level.upper():5}  {text}")
    need = max((c[0] for c in changes if c[0] != "eval"), key=lambda l: RANK[l], default="patch")
    got = bump(ov, nv)
    evals = sum(c[0] == "eval" for c in changes)
    ok = RANK[got] >= RANK[need]
    print(f"needs: {need} bump   declared: {ov} -> {nv} ({got})   -> {'OK' if ok else 'FAIL: version too small for this change'}"
          + (f"\n{evals} description change(s): run the tool-choice eval before release" if evals else ""))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

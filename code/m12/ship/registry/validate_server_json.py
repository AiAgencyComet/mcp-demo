"""Check an MCP registry server.json on this machine only. Nothing is sent anywhere.
(`mcp-publisher validate` is NOT offline: it POSTs the file to <registry>/v0/validate.)
  python validate_server_json.py server.json [bundle.mcpb] [manifest.json]
1. JSON Schema (the published 2025-12-11 schema, saved next to this file)
2. Official-registry rules that can be checked offline (docs: official-registry-requirements.md, package-types.mdx)
3. One version everywhere: server.json, manifest.json and the serverInfo.version that the running server reports"""
import asyncio, hashlib, json, re, sys
from pathlib import Path
from urllib.parse import urlparse

import jsonschema

HERE = Path(__file__).resolve().parent
SCHEMA = json.loads((HERE / "server.schema.2025-12-11.json").read_text())
RANGE = re.compile(r"^[\^~><=]|\.x$|\*")


async def server_version():
    sys.path[:0] = [str(HERE.parents[1]), str(HERE.parents[2] / "fernhill")]
    from mcp import Client
    from releases import fernhill_v1_1
    async with Client(fernhill_v1_1.mcp) as c:
        return c.server_info.version


def check(doc, bundle=None, manifest=None, live_version=None):
    errors = [f"schema: {'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(doc)]
    if doc.get("$schema") != SCHEMA["$id"]:
        errors.append(f"$schema is {doc.get('$schema')!r}, expected {SCHEMA['$id']}")
    v = str(doc.get("version", ""))
    if v == "latest" or RANGE.search(v):
        errors.append(f"version {v!r} is a range or 'latest' (rejected)")
    for k in (doc.get("_meta") or {}):
        if k != "io.modelcontextprotocol.registry/publisher-provided":
            errors.append(f"_meta key {k!r} is dropped by the official registry")
    for p in doc.get("packages", []):
        if p.get("registryType") == "mcpb":
            u = urlparse(p.get("identifier", ""))
            if "mcp" not in p.get("identifier", ""):
                errors.append("mcpb identifier must contain 'mcp'")
            if u.scheme != "https" or u.netloc not in ("github.com", "gitlab.com") or "/releases/" not in u.path:
                errors.append(f"mcpb identifier must be a GitHub or GitLab release URL, got {p.get('identifier')!r}")
            if "fileSha256" not in p:
                errors.append("mcpb package needs fileSha256")
            elif bundle:
                real = hashlib.sha256(Path(bundle).read_bytes()).hexdigest()
                if p["fileSha256"] != real:
                    errors.append(f"fileSha256 {p['fileSha256'][:12]}... != sha256 of {Path(bundle).name} {real[:12]}...")
    if manifest:
        mv = json.loads(Path(manifest).read_text())["version"]
        if mv != v: errors.append(f"version {v} != manifest.json version {mv}")
    if live_version is not None and live_version != v:
        errors.append(f"version {v} != serverInfo.version {live_version!r} reported by the server")
    return errors


def report(title, doc, **kw):
    errs = check(doc, **kw)
    print(f"{title}: {'VALID' if not errs else f'{len(errs)} problem(s)'}")
    for e in errs: print("  -", e)
    return errs


if __name__ == "__main__":
    path, bundle, manifest = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else None
    doc = json.loads(Path(path).read_text())
    live = asyncio.run(server_version())
    print(f"schema {SCHEMA['$id']}  |  serverInfo.version from the v1.1 server: {live!r}\n")
    errs = report("server.json", doc, bundle=bundle, manifest=manifest, live_version=live)

    # the same checks on four broken copies, to show that each rule fires
    print()
    bad = json.loads(json.dumps(doc)); bad["packages"][0]["fileSha256"] = "0" * 64
    report("copy 1: bundle rebuilt, hash not updated", bad, bundle=bundle)
    bad = json.loads(json.dumps(doc)); bad["version"] = "^1.1.0"; bad["name"] = "fernhill coffee"
    report("copy 2: version range + name without namespace", bad)
    bad = json.loads(json.dumps(doc)); bad["description"] = "x" * 101; del bad["packages"][0]["transport"]
    report("copy 3: description 101 chars + no transport", bad)
    bad = json.loads(json.dumps(doc)); bad["version"] = "1.2.0"
    report("copy 4: server.json bumped, bundle and server not", bad, manifest=manifest, live_version=live)
    sys.exit(1 if errs else 0)

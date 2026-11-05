"""Host rule checks for module 8 (a separate run from capture.py; not for the main screen recording).
1. Visibility: the View asks for order_status (visibility ["model"]); the host must refuse it.
2. Deny: the person clicks Deny in the consent dialog; the server state must not change.
3. CSP: the resource declares no ui.csp, so the sandbox gets the restrictive default (connect-src 'none').
4. Origins: the sandbox frame cannot read the host page.
Writes data/m08/checks_transcript.txt, checks_bridge_log.jsonl and screens/check_*.png."""
import asyncio
import json
from pathlib import Path

import httpx
from playwright.async_api import async_playwright

DATA = Path(__file__).resolve().parents[2] / "data" / "m08"
HOST = "http://127.0.0.1:8820/?log=checks_bridge_log&turnDelay=300"
lines = []


def out(s=""):
    print(s)
    lines.append(s)


async def view_frame(page):
    for f in page.frames:
        try:
            if await f.evaluate("!!document.querySelector('.board')"):
                return f
        except Exception:
            pass
    raise RuntimeError("View frame not found")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        page = await ctx.new_page()
        console = []
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        await page.goto(HOST)
        await page.frame_locator("#app-frame").frame_locator("iframe").locator('button[data-done="A-1044"]').wait_for()
        view = await view_frame(page)
        sandbox = next(f for f in page.frames if f.url.startswith("http://localhost:8821/"))
        out(f"frames: host={page.url}")
        out(f"        sandbox proxy={sandbox.url}")
        out(f"        view={view.url!r} (document.write into the proxy's inner iframe), origin={await view.evaluate('origin')}")

        out("\n== 1. visibility: the View calls order_status (visibility [\"model\"]) ==")
        r = await view.evaluate("""request("tools/call", {name: "order_status", arguments: {order_id: "A-1044"}})
                                   .then(r => ({result: r}), e => ({error: e}))""")
        out(f"View got: {json.dumps(r)}")

        out("\n== 2. deny: click Mark done on A-1044, then Deny ==")
        await page.frame_locator("#app-frame").frame_locator("iframe").locator('button[data-done="A-1044"]').click()
        await page.wait_for_selector("body[data-consent=open]")
        await page.locator("#deny").click()
        await page.wait_for_selector("body[data-consent=denied]")
        await page.wait_for_timeout(300)
        toast = await view.evaluate("document.getElementById('toast').textContent")
        out(f"View toast: {toast!r}")
        await page.screenshot(path=DATA / "screens" / "check_deny.png")
        state = await page.evaluate("""mcp("tools/call", {name: "order_status", arguments: {order_id: "A-1044"}}, "check")
                                       .then(r => r.content[0].text)""")
        out(f"server after Deny, order_status A-1044 -> {state!r}")

        out("\n== 3. CSP: no ui.csp declared -> restrictive default ==")
        hdr = httpx.get("http://localhost:8821/sandbox.html").headers.get("content-security-policy")
        out(f"sandbox.html Content-Security-Policy: {hdr}")
        r = await view.evaluate("""new Promise(resolve => {
            const seen = [];
            document.addEventListener("securitypolicyviolation", e => seen.push(e.violatedDirective + " " + e.blockedURI));
            fetch("http://127.0.0.1:8810/mcp", {method: "POST"})
              .then(x => resolve({fetched: x.status, seen}), e => setTimeout(() => resolve({error: String(e), seen}), 100));
        })""")
        out(f"View fetch to the MCP server directly: {json.dumps(r)}")

        out("\n== 4. origins: can the sandbox proxy or the View read the host page? ==")
        for name, frame in (("sandbox proxy", sandbox), ("view", view)):
            r = await frame.evaluate("""(() => { try { return "read: " + window.top.document.title; }
                                                  catch (e) { return e.name + ": " + e.message.split(".")[0]; } })()""")
            out(f"{name}: window.top.document.title -> {r}")

        await page.evaluate("window.__flushLog()")
        await ctx.close()
        await browser.close()
    out("\nconsole:")
    for c in console:
        out("  " + c[:220])
    (DATA / "checks_transcript.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())

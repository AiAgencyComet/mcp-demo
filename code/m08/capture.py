"""Drive the local test host with Playwright (headless Chromium, 1280x720 CSS px at device_scale_factor 2
= 2560x1440 screenshots). Steps: connect, board loading, board loaded, click "Mark done" on A-1043,
consent dialog, Allow, result, model context, teardown. Saves screenshots, a video and the bridge log.
The video is a loop of page.screenshot() calls (2560x1440, about 30 per second), placed on a 30 fps timeline
by capture time. Playwright's recorder and the CDP screencast give CSS-pixel frames (1280x720) at DPR 2, and
CDP captureScreenshot with clip.scale 2 resizes the page while it shoots (the View then sends size-changed).
Needs: MCP server on 127.0.0.1:8810 and host_server.py running (see run_capture.sh)."""
import asyncio
import base64
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

DATA = Path(__file__).resolve().parents[2] / "data" / "m08"
SHOTS = DATA / "screens"
FRAMES = DATA / "frames_tmp"
HOST = "http://127.0.0.1:8820/"
W, H = 1280, 720
ORDER = "A-1043"


async def main():
    SHOTS.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(FRAMES, ignore_errors=True)
    FRAMES.mkdir()
    frames = []  # (timestamp in seconds, path)
    console = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=2)
        page = await ctx.new_page()
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))

        recording = True
        skipped = []

        async def record():
            # device-pixel screenshots in a loop; each frame keeps its capture time
            while recording:
                t = time.monotonic()
                try:
                    data = await page.screenshot(type="jpeg", quality=92, animations="allow")
                except Exception as err:  # e.g. while the page navigates; skip this frame
                    skipped.append(str(err)[:80])
                    await asyncio.sleep(0.02)
                    continue
                path = FRAMES / f"{len(frames):05d}.jpg"
                path.write_bytes(data)
                frames.append((t, path))

        recorder = asyncio.create_task(record())

        await page.goto(HOST + "?hold=1800&turnDelay=1400")
        await page.wait_for_selector("body[data-state=connected]")
        await page.wait_for_timeout(300)
        await page.screenshot(path=SHOTS / "01_host_connected.png")

        view = page.frame_locator("#app-frame").frame_locator("iframe")
        await view.locator(".skel").first.wait_for()
        await page.wait_for_timeout(250)
        await page.screenshot(path=SHOTS / "02_board_loading.png")

        await view.locator(f'button[data-done="{ORDER}"]').wait_for()
        await page.wait_for_timeout(700)
        await page.screenshot(path=SHOTS / "03_board_loaded.png")
        await page.locator(".card").screenshot(path=SHOTS / "03b_board_card.png")

        btn = view.locator(f'button[data-done="{ORDER}"]')
        await btn.hover()
        await page.wait_for_timeout(500)
        await btn.click()
        await page.wait_for_selector("body[data-consent=open]")
        await page.wait_for_timeout(600)
        await page.screenshot(path=SHOTS / "04_consent.png")

        await page.locator("#allow").hover()
        await page.wait_for_timeout(400)
        await page.locator("#allow").click()
        await view.locator(f'li[data-id="{ORDER}"].is-done').wait_for()
        await page.wait_for_timeout(350)
        await page.screenshot(path=SHOTS / "05_marked_done.png")
        await page.locator(".card").screenshot(path=SHOTS / "05b_board_card_done.png")

        await page.wait_for_selector("body[data-context=set]")
        await page.wait_for_timeout(1800)
        await page.screenshot(path=SHOTS / "06_model_context.png")

        fit = await page.evaluate("""(() => { const c = document.getElementById('chat');
            return {chat_overflow_px: c.scrollHeight - c.clientHeight,
                    frame_height_px: document.getElementById('app-frame').clientHeight}; })()""")
        print("layout check:", fit)
        teardown = await page.evaluate("window.teardown()")
        await page.wait_for_timeout(600)
        await page.screenshot(path=SHOTS / "07_after_teardown.png")
        await page.evaluate("window.__flushLog()")
        log = await page.evaluate("window.__bridgeLog")
        await page.wait_for_timeout(400)
        recording = False
        await recorder
        print(f"recorder: {len(frames)} frames, {len(skipped)} skipped", sorted(set(skipped))[:3])
        await ctx.close()
        await browser.close()

    # the page appended every entry to bridge_log.jsonl through /api/log; check it matches the in-page log
    on_disk = [json.loads(line) for line in (DATA / "bridge_log.jsonl").read_text().splitlines() if line]
    print(f"bridge log: {len(log)} entries in page, {len(on_disk)} on disk")
    (DATA / "console.txt").write_text("\n".join(console) + "\n")
    print("teardown result:", teardown)
    print("console lines:", len(console))
    for line in console:
        print("  ", line[:200])

    # constant 30 fps at real speed: output frame k shows the last capture taken at or before k/30 s
    seq_dir = FRAMES / "seq"
    seq_dir.mkdir()
    t0, i = frames[0][0], 0
    n_out = int((frames[-1][0] - t0) * 30) + 1
    for k in range(n_out):
        while i + 1 < len(frames) and frames[i + 1][0] - t0 <= k / 30:
            i += 1
        (seq_dir / f"{k:05d}.jpg").hardlink_to(frames[i][1])
    mp4 = DATA / "host_run.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", str(seq_dir / "%05d.jpg"),
                    "-vf", "format=yuv420p", "-c:v", "libx264", "-crf", "14", "-preset", "slow", str(mp4)], check=True)
    print(f"video: {mp4} from {len(frames)} frames over {frames[-1][0] - frames[0][0]:.1f} s "
          f"({len(frames) / (frames[-1][0] - frames[0][0]):.1f} captures per second)")
    shutil.rmtree(FRAMES, ignore_errors=True)
    print("screens:", sorted(x.name for x in SHOTS.iterdir()))


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)

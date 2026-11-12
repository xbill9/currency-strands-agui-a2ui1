"""Screenshot the chat panel for each demo prompt.

usage: python3 -I shoot.py OUT_DIR name=prompt [name=prompt ...]
Each prompt runs on a fresh page load (a new thread). Waits until the panel
text stops changing for 5 s after the reply starts, then captures the panel.
"""

import os
import sys
import time

from playwright.sync_api import sync_playwright

HIDE = """
() => {
  for (const el of document.querySelectorAll('nextjs-portal, cpk-web-inspector')) el.remove();
  for (const el of document.querySelectorAll('div, aside, section')) {
    const t = (el.innerText || '').trim();
    if (t.startsWith('AG-UI 1.0 is here') && el.getBoundingClientRect().width < 700) {
      let n = el;
      while (n.parentElement && (n.parentElement.innerText || '').trim() === t) n = n.parentElement;
      n.style.display = 'none';
    }
  }
}
"""

PANEL = """
() => {
  let n = document.querySelector('textarea');
  while (n && n.getBoundingClientRect().height < window.innerHeight * 0.9) n = n.parentElement;
  const r = n.getBoundingClientRect();
  return {x: r.x, y: r.y, width: r.width, height: r.height, text: n.innerText};
}
"""


CROP = """
(prompt) => {
  const all = [...document.querySelectorAll('div, p, span')];
  const bubble = all.filter(e => (e.innerText || '').trim() === prompt)
                    .sort((a, b) => a.getBoundingClientRect().width - b.getBoundingClientRect().width)[0];
  const chip = [...document.querySelectorAll('button')].find(b => (b.innerText || '').trim() === 'Convert USD to EUR');
  const input = document.querySelector('textarea');
  const end = chip || input;
  return {top: bubble.getBoundingClientRect().top, bottom: end.getBoundingClientRect().top};
}
"""


def shoot(page, prompt, path, full=False):
    page.goto(os.environ.get("UI_URL", "http://localhost:3001"), wait_until="networkidle", timeout=120000)
    page.wait_for_timeout(1500)
    page.evaluate(HIDE)
    base = page.evaluate(PANEL)["text"]
    page.fill("textarea", prompt)
    page.keyboard.press("Enter")
    deadline = time.time() + 90
    last, stable_since = None, None
    while time.time() < deadline:
        page.wait_for_timeout(500)
        page.evaluate(HIDE)
        cur = page.evaluate(PANEL)
        grew = len(cur["text"]) > len(base) + len(prompt) + 20
        if cur["text"] != last:
            last, stable_since = cur["text"], time.time()
        elif grew and time.time() - stable_since > 5:
            break
    page.wait_for_timeout(800)
    box = page.evaluate(PANEL)
    if full:
        page.screenshot(path=path)
        return box["text"]
    crop = page.evaluate(CROP, prompt)
    top = max(box["y"], crop["top"] - 24)
    bottom = crop["bottom"] - 10
    page.screenshot(
        path=path,
        clip={"x": box["x"], "y": top, "width": box["width"], "height": bottom - top},
    )
    return box["text"]


if __name__ == "__main__":
    out = sys.argv[1]
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(
            viewport={"width": 1200, "height": 1700}, device_scale_factor=2
        )
        for arg in sys.argv[2:]:
            name, prompt = arg.split("=", 1)
            full = name.startswith("full-")
            if full:
                page.set_viewport_size({"width": 1440, "height": 900})
            else:
                page.set_viewport_size({"width": 1200, "height": 1700})
            text = shoot(page, prompt, f"{out}/{name}.png", full=full)
            print(f"== {name}: {prompt}\n{text}\n")
        browser.close()

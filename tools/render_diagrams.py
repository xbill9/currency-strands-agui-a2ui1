"""Render the .mmd diagrams to PNG with Mermaid in headless Chrome.

usage: python3 render_diagrams.py DIAGRAM_DIR OUT_DIR
"""

import html
import pathlib
import sys

from playwright.sync_api import sync_playwright

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
<style>body{margin:0;padding:24px;background:#fff;font-family:Inter,Arial,sans-serif}</style>
</head><body><pre class="mermaid">%s</pre>
<script>mermaid.initialize({startOnLoad:false,theme:"base",
  themeVariables:{fontFamily:"Inter, Arial, sans-serif",fontSize:"16px",lineColor:"#475569"}});
mermaid.run().then(()=>document.body.dataset.done="1");</script></body></html>"""

src, out = map(pathlib.Path, sys.argv[1:3])
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(
        device_scale_factor=2, viewport={"width": 1400, "height": 900}
    )
    for mmd in sorted(src.glob("*.mmd")):
        page.set_content(PAGE % html.escape(mmd.read_text()))
        page.wait_for_selector("body[data-done='1']", timeout=60000)
        page.locator("pre.mermaid svg").screenshot(path=str(out / f"{mmd.stem}.png"))
        print("wrote", out / f"{mmd.stem}.png")
    browser.close()

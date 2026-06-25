"""Capture a screenshot of the deployed Streamlit app for portfolio embedding.

Headless Chromium via playwright; waits long enough for the pydeck map and
sidebar to render, then writes a PNG.

Usage:
    python scripts/screenshot_streamlit.py \\
        --url https://cogsieve-vir5swvkd2a5fypnpyqlnn.streamlit.app/ \\
        --out ../ahotimski00.github.io/assets/img/cogsieve_streamlit.png
"""

from __future__ import annotations

from pathlib import Path

import typer
from playwright.sync_api import sync_playwright
from rich.console import Console

app = typer.Typer(add_completion=False)
console = Console()


@app.command()
def main(
    url: str = typer.Option(..., help="Streamlit app URL."),
    out: Path = typer.Option(..., help="Output PNG path."),
    width: int = typer.Option(1600, help="Viewport width."),
    height: int = typer.Option(1000, help="Viewport height."),
    wait_seconds: int = typer.Option(20, help="Render budget after page load."),
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": width, "height": height})
        page = ctx.new_page()
        console.print(f"navigating to {url}")
        # Streamlit holds a persistent websocket so 'networkidle' never fires;
        # use domcontentloaded and a generous settle timer instead.
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        console.print(f"waiting {wait_seconds}s for pydeck + Streamlit to settle")
        page.wait_for_timeout(wait_seconds * 1000)
        page.screenshot(path=str(out), full_page=False)
        size_kb = out.stat().st_size / 1024
        console.print(f"[bold green]saved[/bold green] {out} ({size_kb:.0f} KB)")
        browser.close()


if __name__ == "__main__":
    app()

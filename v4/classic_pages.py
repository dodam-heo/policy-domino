"""Deterministic static page rendering for two routes with one template.

Source of truth: site/templates/agency.html and site/assets/*.
The build may update generated HTML, but business logic must not rewrite markup.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "site" / "templates" / "agency.html"
DATA_URL_BY_ROUTE = {
    "classic": "./data.json",
    "impact": "../classic/data.json",
}
TOKEN = "__POLICY_DATA_URL__"


def render_page(route: str) -> str:
    if route not in DATA_URL_BY_ROUTE:
        raise ValueError(f"Unsupported page route: {route}")
    html = TEMPLATE.read_text(encoding="utf-8")
    if html.count(TOKEN) != 1:
        raise ValueError("Page template requires exactly one data-path token")
    return html.replace(TOKEN, DATA_URL_BY_ROUTE[route])


def publish_pages() -> None:
    for route in DATA_URL_BY_ROUTE:
        target = ROOT / "site" / route / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        output = render_page(route)
        if not target.exists() or target.read_text(encoding="utf-8") != output:
            target.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    publish_pages()

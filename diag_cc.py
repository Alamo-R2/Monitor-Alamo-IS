#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnostico de Ciencuadras: que ve Playwright en el runner de GitHub Actions."""
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://www.ciencuadras.com/venta/bogota/chapinero/apartamento"
out = {"url": URL}

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(
        locale="es-CO",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    )
    pg = ctx.new_page()
    try:
        pg.goto(URL, timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        out["goto_error"] = str(e)
    pg.wait_for_timeout(6000)
    try:
        pg.wait_for_selector("a[href*='/inmueble/']", timeout=10000)
        out["wait_selector"] = "ok"
    except Exception as e:
        out["wait_selector"] = "timeout: " + str(e)[:120]
    html = pg.content()
    out["title"] = pg.title()
    out["url_final"] = pg.url
    out["html_len"] = len(html)
    out["anchors_inmueble_dom"] = len(pg.query_selector_all("a[href*='/inmueble/']"))
    out["html_inmueble_regex"] = len(set(re.findall(r"/inmueble/[a-z0-9-]+-\d+", html)))
    marcadores = ["cloudflare", "challenge", "captcha", "robot", "verifica que eres",
                  "attention required", "just a moment", "cf-browser-verification",
                  "access denied", "forbidden", "datadome", "px-captcha"]
    out["marcadores_bloqueo"] = [m for m in marcadores if m in html.lower()]
    a = pg.query_selector("a[href*='/inmueble/']")
    try:
        out["primer_anchor_text"] = (a.inner_text()[:400] if a else None)
    except Exception as e:
        out["primer_anchor_text"] = "err: " + str(e)[:100]
    try:
        out["body_snippet"] = re.sub(r"\s+", " ", pg.inner_text("body"))[:700]
    except Exception as e:
        out["body_snippet"] = "err: " + str(e)[:100]
    b.close()

Path("pruebas").mkdir(exist_ok=True)
Path("pruebas/diag_ciencuadras.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
Path("pruebas/cc_raw.html").write_text(html, encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "body_snippet"}, ensure_ascii=False, indent=2))

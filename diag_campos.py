#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vuelca las claves crudas de un item de metrocuadrado y de fincaraiz."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
RES = {}


def abrir(p, url):
    pg = p.chromium.launch(headless=True).new_context(locale="es-CO", user_agent=UA).new_page()
    pg.goto(url, timeout=60000, wait_until="domcontentloaded")
    pg.wait_for_timeout(6000)
    return pg


def _plano(d):
    return {k: v for k, v in d.items() if not isinstance(v, (dict, list))}


with sync_playwright() as p:
    # ---- metrocuadrado: initialResults en el HTML ----
    try:
        pg = abrir(p, "https://www.metrocuadrado.com/apartamento/venta/bogota/chapinero/")
        html = pg.content()
        a = html.find("initialResults")
        rk = html.find("results", a)
        br = html.find("[", rk)
        depth, i, end = 0, br, -1
        while i < len(html):
            if html[i] == "[":
                depth += 1
            elif html[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        raw = html[br:end + 1]
        results = None
        for fn in (lambda s: json.loads(s),
                   lambda s: json.loads(s.replace('\\"', '"').replace("\\\\", "\\")),
                   lambda s: json.loads(s.encode("utf-8").decode("unicode_escape"))):
            try:
                results = fn(raw)
                if isinstance(results, list) and results:
                    break
            except Exception:
                results = None
        if results:
            it = results[0]
            RES["metrocuadrado_keys"] = sorted(it.keys())
            RES["metrocuadrado_plano"] = _plano(it)
            RES["metrocuadrado_data_keys"] = sorted((it.get("data") or {}).keys()) if isinstance(it.get("data"), dict) else None
        else:
            RES["metrocuadrado_err"] = "no results"
    except Exception as e:
        RES["metrocuadrado_err"] = str(e)[:200]

    # ---- fincaraiz: __NEXT_DATA__ searchFast.data ----
    try:
        pg = abrir(p, "https://www.fincaraiz.com.co/venta/apartamentos/chapinero/bogota?pagina=1")
        el = pg.query_selector("#__NEXT_DATA__")
        data = json.loads(el.inner_text())
        arr = data["props"]["pageProps"]["fetchResult"]["searchFast"]["data"]
        it = arr[0]
        RES["fincaraiz_keys"] = sorted(it.keys())
        RES["fincaraiz_plano"] = _plano(it)
    except Exception as e:
        RES["fincaraiz_err"] = str(e)[:200]

Path("pruebas").mkdir(exist_ok=True)
Path("pruebas/diag_campos.json").write_text(json.dumps(RES, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({k: (v if "keys" in k or "err" in k else "...") for k, v in RES.items()}, ensure_ascii=False, indent=2))

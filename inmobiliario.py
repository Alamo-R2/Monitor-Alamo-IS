python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MONITOR INMOBILIARIO — Opción B. Comandos: buscar avaluo noticias doctor publicar diagnostico"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
    import requests
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Faltan librerias. Ver GUIA_MANTENIMIENTO.md")
    sys.exit(1)

CIUDAD_POR_DEFECTO = "bogota"

PORTALES = {
    "metrocuadrado": {
        "url": "https://www.metrocuadrado.com/{tipo}/{operacion}/{ciudad}/{zona}/?page={pagina}",
        "css_tarjeta": "div[data-id]", "css_precio": "[class*='price']",
        "css_titulo": "h2", "css_area": "[class*='area']",
        "css_hab": "[class*='bed']", "css_ubic": "[class*='location']",
    },
    "fincaraiz": {
        "url": "https://www.fincaraiz.com.co/{operacion}/{tipo}/{ciudad}/{zona}?pagina={pagina}",
        "css_tarjeta": "article", "css_precio": "[class*='price']",
        "css_titulo": "h2", "css_area": "[class*='area']",
        "css_hab": "[class*='room']", "css_ubic": "[class*='location']",
    },
}

NOTICIAS = {
    "La Republica": "https://www.larepublica.co/camacol",
    "Portafolio": "https://www.portafolio.co/noticias-economicas/sector-inmobiliario",
    "Valora Analitik": "https://www.valoraanalitik.com/",
    "El Colombiano": "https://www.elcolombiano.com/cronologia/noticias/meta/sector-inmobiliario",
    "Oikos": "https://www.oikos.com.co/inmobiliaria/noticias-inmobiliaria",
    "Camacol": "https://camacol.co/actualidad/noticias",
}

PAUSA = 2.5
PAGINAS_POR_DEFECTO = 5

PUBLICAR = [
    {"clave": "venta_apto_chapinero", "etiqueta": "Venta - Apto - Chapinero",
     "portal": "metrocuadrado", "operacion": "venta", "tipo": "apartamento", "zona": "chapinero"},
    {"clave": "arriendo_apto_chapinero", "etiqueta": "Arriendo - Apto - Chapinero",
     "portal": "metrocuadrado", "operacion": "arriendo", "tipo": "apartamento", "zona": "chapinero"},
]
PUBLICAR_NOTICIAS = True


def _num(texto):
    if not texto:
        return None
    d = re.sub(r"[^\d]", "", str(texto))
    return int(d) if d else None


def _dec(valor):
    if valor is None or valor == "":
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        s = re.sub(r"[^\d.,]", "", str(valor)).replace(",", ".")
        try:
            return float(s) if s else None
        except ValueError:
            return None


def _carpeta(nombre):
    p = Path(nombre)
    p.mkdir(exist_ok=True)
    return p


def _abrir_pagina(browser, url):
    page = browser.new_context(
        locale="es-CO",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    ).new_page()
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    return page


def _desde_metrocuadrado(page):
    html = page.content()
    idx = html.find('\\"initialResults\\"')
    if idx < 0:
        idx = html.find('"initialResults"')
    if idx < 0:
        return []
    rkey = html.find('results', idx)
    if rkey < 0:
        return []
    br = html.find('[', rkey)
    if br < 0:
        return []
    depth, i, in_str, esc = 0, br, False, False
    while i < len(html):
        c = html[i]
        if esc:
            esc = False
        elif c == '\\':
            esc = True
        elif c == '"':
            in_str = not in_str
        elif not in_str:
            if c == '[':
                depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0:
                    break
        i += 1
    raw = html[br:i + 1]
    try:
        results = json.loads(raw.encode('utf-8').decode('unicode_escape'))
    except Exception:
        try:
            results = json.loads(raw.replace('\\"', '"').replace('\\\\', '\\'))
        except Exception:
            return []
    filas = []
    for r in results:
        if not isinstance(r, dict):
            continue
        precio = r.get("mvalorventa") or r.get("mvalorarriendo")
        loc = r.get("localizacion") or {}
        data = r.get("data") or {}
        link = r.get("link") or data.get("murldetalle")
        filas.append({
            "titulo": r.get("title"),
            "precio": _num(precio),
            "area_m2": _dec(r.get("marea") or r.get("mareac")),
            "habitaciones": _num(r.get("mnrocuartos")),
            "banos": _num(r.get("mnrobanos")),
            "parqueaderos": _num(r.get("mnrogarajes")),
            "administracion": _num(data.get("mvaloradministracion")),
            "ubicacion": r.get("mbarrio") or (r.get("mzona") or {}).get("nombre"),
            "url": ("https://www.metrocuadrado.com" + link) if link and link.startswith("/") else link,
            "id_domus": r.get("midinmueble"),
            "lat": loc.get("lat"),
            "lon": loc.get("lon"),
            "location_type": "exacta" if loc.get("lat") else "aproximada",
            "_fuente": "metrocuadrado-next",
        })
    return filas


def _desde_fincaraiz(page):
    el = page.query_selector("#__NEXT_DATA__")
    if not el:
        return []
    try:
        data = json.loads(el.inner_text())
    except Exception:
        return []
    try:
        arr = data["props"]["pageProps"]["fetchResult"]["searchFast"]["data"]
    except Exception:
        return []
    filas = []
    for r in arr:
        if not isinstance(r, dict):
            continue
        precio = (r.get("price") or {}).get("amount")
        admin = (r.get("commonExpenses") or {}).get("amount")
        loc = r.get("locations") or {}
        barrio = (loc.get("location_main") or {}).get("name")
        link = r.get("link")
        filas.append({
            "titulo": r.get("title"),
            "precio": _num(precio),
            "area_m2": _dec(r.get("m2") or r.get("m2Built") or r.get("m2apto")),
            "habitaciones": _num(r.get("bedrooms")),
            "banos": _num(r.get("bathrooms")),
            "parqueaderos": _num(r.get("garage")),
            "administracion": _num(admin) if admin else None,
            "ubicacion": barrio,
            "url": ("https://www.fincaraiz.com.co" + link) if link and link.startswith("/") else link,
            "id_domus": str(r.get("id")) if r.get("id") else None,
            "lat": r.get("latitude"),
            "lon": r.get("longitude"),
            "location_type": "exacta" if r.get("latitude") else "aproximada",
            "_fuente": "fincaraiz-next",
        })
    return filas


def _desde_css(page, cfg):
    filas = []
    for t in page.query_selector_all(cfg["css_tarjeta"]):
        def tx(sel):
            e = t.query_selector(sel)
            return e.inner_text().strip() if e else None
        link = t.query_selector("a")
        href = link.get_attribute("href") if link else None
        filas.append({
            "titulo": tx(cfg["css_titulo"]),
            "precio": _num(tx(cfg["css_precio"])),
            "area_m2": _dec(tx(cfg["css_area"])),
            "habitaciones": _num(tx(cfg["css_hab"])),
            "ubicacion": tx(cfg["css_ubic"]),
            "url": href,
            "_fuente": "css",
        })
    return filas


def _validar(filas, min_filas=3, max_vacios=0.4):
    problemas = []
    if len(filas) < min_filas:
        problemas.append("pocos resultados (" + str(len(filas)) + ")")
    if filas:
        vacios = sum(1 for f in filas if not f.get("precio")) / len(filas)
        if vacios > max_vacios:
            problemas.append("precios vacios")
    return (len(problemas) == 0), problemas


def extraer(page, cfg):
    for estrategia in (_desde_metrocuadrado, _desde_fincaraiz):
        filas = estrategia(page)
        if _validar(filas)[0]:
            return filas
    return _desde_css(page, cfg)
    def scrape_portal(portal, operacion, tipo, zona, ciudad, paginas):
    cfg = PORTALES[portal]
    todos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for n in range(1, paginas + 1):
            url = cfg["url"].format(operacion=operacion, tipo=tipo, zona=zona, ciudad=ciudad, pagina=n)
            print("  [" + portal + " " + str(n) + "/" + str(paginas) + "] leyendo...")
            try:
                page = _abrir_pagina(browser, url)
                filas = extraer(page, cfg)
                if not filas:
                    break
                todos.extend(filas)
            except Exception as e:
                print("    aviso: " + str(e))
            time.sleep(PAUSA)
        browser.close()
    vistos, unicos = set(), []
    for f in todos:
        k = f.get("url") or json.dumps(f, ensure_ascii=False)
        if k not in vistos:
            vistos.add(k)
            unicos.append(f)
    return unicos


def resumen_mercado(df):
    if df.empty or "precio" not in df:
        return {}
    precios = df["precio"].dropna()
    if precios.empty:
        return {}
    res = {
        "resultados": int(len(df)),
        "precio_min": int(precios.min()),
        "precio_max": int(precios.max()),
        "precio_promedio": int(precios.mean()),
        "precio_mediana": int(precios.median()),
    }
    if "area_m2" in df:
        m2 = df.dropna(subset=["precio", "area_m2"])
        m2 = m2[m2["area_m2"] > 0]
        if not m2.empty:
            res["precio_m2_promedio"] = int((m2["precio"] / m2["area_m2"]).mean())
    return res


def leer_noticias():
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MonitorInmobiliario/1.0)"}
    for medio, url in NOTICIAS.items():
        try:
            r = requests.get(url, headers=headers, timeout=20)
            titulares = re.findall(r"<h[12][^>]*>\s*(?:<a[^>]*>)?\s*([^<]{25,140})", r.text)
            for t in titulares[:5]:
                t = re.sub(r"\s+", " ", t).strip()
                if t:
                    items.append({"medio": medio, "titular": t, "url": url})
        except Exception as e:
            print("  aviso (" + medio + "): " + str(e))
    return items


def exportar_excel(df, resumen, etiqueta):
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / (etiqueta + "_" + fecha + ".xlsx")
    with pd.ExcelWriter(ruta, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="Listados", index=False)
        if resumen:
            pd.DataFrame([resumen]).T.rename(columns={0: "valor"}).to_excel(xl, sheet_name="Resumen_mercado")
    return ruta


def _df_a_contrato(df, portal, operacion, tipo):
    oper = {"venta": "Venta", "arriendo": "Arriendo"}.get(operacion, operacion)
    inmuebles = []
    for idx, r in df.reset_index(drop=True).iterrows():
        def g(k):
            v = r.get(k)
            return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
        inmuebles.append({
            "id": "MI-" + str(idx + 1),
            "operacion": [oper],
            "tipo": tipo,
            "precio": g("precio"),
            "area": g("area_m2"),
            "administracion": g("administracion"),
            "barrio": (str(g("ubicacion")).upper() if g("ubicacion") else ""),
            "direccion": "",
            "habitaciones": g("habitaciones"),
            "banos": g("banos"),
            "parqueaderos": g("parqueaderos"),
            "portalNombre": portal,
            "sourceLink": g("url"),
            "titulo": g("titulo"),
            "id_domus": g("id_domus"),
            "lat": g("lat"),
            "lon": g("lon"),
            "location_type": g("location_type") or "aproximada",
        })
    return inmuebles


def exportar_alamo_json(df, args, etiqueta):
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / (etiqueta + "_" + fecha + "_alamo.json")
    inmuebles = _df_a_contrato(df, args.portal, args.operacion, args.tipo)
    payload = {"ok": True, "total": len(inmuebles), "inmuebles": inmuebles}
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def exportar_noticias_json(items):
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / ("noticias_" + fecha + "_alamo.json")
    noticias = [{"titulo": it.get("titular", ""), "fuente": it.get("medio", ""),
                 "fecha": datetime.now().strftime("%Y-%m-%d"), "resumen": "",
                 "url": it.get("url", "")} for it in items]
    ruta.write_text(json.dumps({"noticias": noticias}, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def diagnostico(carpeta="data"):
    base = Path(carpeta) / "diagnostico"
    base.mkdir(parents=True, exist_ok=True)
    casos = []
    for portal, cfg in PORTALES.items():
        for oper in ("venta", "arriendo"):
            url = cfg["url"].format(tipo="apartamento", operacion=oper, ciudad=CIUDAD_POR_DEFECTO, zona="chapinero", pagina=1)
            casos.append((portal + "_" + oper, portal, url))
    resumen = {"generado": datetime.now().isoformat(timespec="seconds"), "casos": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for nombre, portal, url in casos:
            info = {"nombre": nombre, "portal": portal, "url": url}
            try:
                page = _abrir_pagina(browser, url)
                info["url_final"] = page.url
                info["titulo"] = page.title()
                info["next_data"] = bool(page.query_selector("#__NEXT_DATA__"))
                html = page.content()
                (base / (nombre + ".html")).write_text(html, encoding="utf-8")
                nd = page.query_selector("#__NEXT_DATA__")
                if nd:
                    (base / (nombre + "__NEXT_DATA__.json")).write_text(nd.inner_text(), encoding="utf-8")
            except Exception as e:
                info["error"] = str(e)
            resumen["casos"].append(info)
            print("  " + nombre + " -> next=" + str(info.get("next_data")))
        browser.close()
    (base / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumen


def publicar(carpeta="data"):
    base = Path(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    generado = datetime.now()
    MES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
    datasets = []
    for cfg in PUBLICAR:
        print("\n== Publicando: " + cfg["etiqueta"] + " ==")
        try:
            filas = scrape_portal(cfg["portal"], cfg["operacion"], cfg["tipo"], cfg["zona"], CIUDAD_POR_DEFECTO, PAGINAS_POR_DEFECTO)
            df = pd.DataFrame(filas)
            inmuebles = _df_a_contrato(df, cfg["portal"], cfg["operacion"], cfg["tipo"]) if not df.empty else []
        except Exception as e:
            print("  aviso: " + str(e))
            inmuebles = []
        archivo = cfg["clave"] + ".json"
        (base / archivo).write_text(json.dumps({"ok": True, "total": len(inmuebles), "inmuebles": inmuebles}, ensure_ascii=False, indent=2), encoding="utf-8")
        datasets.append({"clave": cfg["clave"], "etiqueta": cfg["etiqueta"], "archivo": archivo,
                         "total": len(inmuebles), "operacion": cfg["operacion"], "tipo": cfg["tipo"], "zona": cfg["zona"]})
        print("  " + str(len(inmuebles)) + " inmueble(s) -> " + archivo)
    noticias_meta = None
    if PUBLICAR_NOTICIAS:
        try:
            items = leer_noticias()
        except Exception as e:
            print("  aviso noticias: " + str(e))
            items = []
        noticias = [{"titulo": it.get("titular", ""), "fuente": it.get("medio", ""),
                     "fecha": generado.strftime("%Y-%m-%d"), "resumen": "", "url": it.get("url", "")} for it in items]
        (base / "noticias.json").write_text(json.dumps({"noticias": noticias}, ensure_ascii=False, indent=2), encoding="utf-8")
        noticias_meta = {"archivo": "noticias.json", "total": len(noticias)}
    manifiesto = {
        "generado": generado.isoformat(timespec="seconds"),
        "generado_humano": generado.strftime("%Y.") + MES[generado.month - 1] + generado.strftime(".%d %H:%M"),
        "ciudad": CIUDAD_POR_DEFECTO, "datasets": datasets, "noticias": noticias_meta,
    }
    (base / "index.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nUltima corrida: " + manifiesto["generado_humano"])
    return manifiesto


def doctor():
    print("Revisando portales...\n")
    for portal, cfg in PORTALES.items():
        url = cfg["url"].format(operacion="venta", tipo="apartamento", ciudad=CIUDAD_POR_DEFECTO, zona="chapinero", pagina=1)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = _abrir_pagina(browser, url)
                filas = extraer(page, cfg)
                ok, problemas = _validar(filas)
                browser.close()
            print("[" + ("OK" if ok else "REVISAR") + "] " + portal + ": " + str(len(filas)) + " resultado(s). " + "; ".join(problemas))
        except Exception as e:
            print("[ERROR] " + portal + ": " + str(e))


def main():
    parser = argparse.ArgumentParser(description="Monitor Inmobiliario")
    sub = parser.add_subparsers(dest="cmd")
    for cmd in ("buscar", "avaluo"):
        pp = sub.add_parser(cmd)
        pp.add_argument("--portal", default="metrocuadrado")
        pp.add_argument("--operacion", default="venta")
        pp.add_argument("--tipo", default="apartamento")
        pp.add_argument("--zona", default="chapinero")
        pp.add_argument("--ciudad", default=CIUDAD_POR_DEFECTO)
        pp.add_argument("--paginas", type=int, default=PAGINAS_POR_DEFECTO)
    sub.add_parser("noticias")
    sub.add_parser("doctor")
    p1 = sub.add_parser("publicar")
    p1.add_argument("--carpeta", default="data")
    p2 = sub.add_parser("diagnostico")
    p2.add_argument("--carpeta", default="data")
    args = parser.parse_args()
    if args.cmd == "doctor":
        doctor()
    elif args.cmd == "publicar":
        publicar(args.carpeta)
    elif args.cmd == "diagnostico":
        diagnostico(args.carpeta)
    elif args.cmd == "noticias":
        items = leer_noticias()
        for it in items:
            print("\n[" + it["medio"] + "] " + it["titular"])
        exportar_noticias_json(items)
    elif args.cmd in ("buscar", "avaluo"):
        etiqueta = args.cmd + "_" + args.operacion + "_" + args.tipo + "_" + args.zona
        filas = scrape_portal(args.portal, args.operacion, args.tipo, args.zona, args.ciudad, args.paginas)
        df = pd.DataFrame(filas)
        if df.empty:
            print("No se encontraron resultados. Corre 'doctor'.")
            return
        resumen = resumen_mercado(df)
        print("\nResumen de mercado:")
        for k, v in resumen.items():
            print("  " + k + ": " + str(v))
        exportar_excel(df, resumen, etiqueta)
        exportar_alamo_json(df, args, etiqueta)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()


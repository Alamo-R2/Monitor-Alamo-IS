#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MONITOR INMOBILIARIO — Opción B. Comandos: buscar avaluo noticias doctor publicar diagnostico"""
import argparse
import json
import re
import sys
import time
import math
import unicodedata
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
PAGINAS_POR_DEFECTO = 1   # Metrocuadrado entrega ~50 en la 1a pagina; mas paginas no agregan (probado)

PUBLICAR = [
    {"clave": "venta_apto_chapinero", "etiqueta": "Venta - Apto - Chapinero",
     "portal": "metrocuadrado", "operacion": "venta", "tipo": "apartamento", "zona": "chapinero"},
    {"clave": "arriendo_apto_chapinero", "etiqueta": "Arriendo - Apto - Chapinero",
     "portal": "metrocuadrado", "operacion": "arriendo", "tipo": "apartamento", "zona": "chapinero"},
]
PUBLICAR_NOTICIAS = True


# ============================================================================
#  ZONAS POR FRECUENCIA. El workflow pasa --grupo. Cada zona:
#  ("Nombre visible", "slug-en-url", "origen")  origen = "upl" o "barrio"
# ============================================================================
ZONAS_DIARIO = [
    ("Centro Historico", "centro-historico", "upl"),
    ("Teusaquillo", "teusaquillo", "upl"),
    ("Puente Aranda", "puente-aranda", "upl"),
    ("Barrios Unidos", "barrios-unidos", "upl"),
    ("Chapinero", "chapinero", "upl"),
    ("Britalia", "britalia", "upl"),
    ("Toberin", "toberin", "upl"),
    ("Usaquen", "usaquen", "upl"),
    ("Niza", "niza", "upl"),
    ("Fontibon", "fontibon", "upl"),
    ("Engativa", "engativa", "upl"),
]
ZONAS_CADA5 = [
    ("Restrepo", "restrepo", "upl"),
    ("Salitre", "salitre", "upl"),
    ("Torca", "torca", "upl"),
    ("Suba", "suba", "upl"),
    ("Rincon de Suba", "rincon-de-suba", "upl"),
    ("Tibabuyes", "tibabuyes", "upl"),
]
ZONAS_CADA10 = [
    ("Tabora", "tabora", "upl"),
    ("Bosa", "bosa", "upl"),
    ("Tintal", "tintal", "upl"),
    ("Kennedy", "kennedy", "upl"),
    ("Patio Bonito", "patio-bonito", "upl"),
    ("Eden", "eden", "upl"),
    ("Porvenir", "porvenir", "upl"),
    ("Arborizadora", "arborizadora", "upl"),
    ("Lucero", "lucero", "upl"),
    ("Tunjuelito", "tunjuelito", "upl"),
    ("Rafael Uribe", "rafael-uribe", "upl"),
    ("Usme Entrenubes", "usme-entrenubes", "upl"),
    ("San Cristobal", "san-cristobal", "upl"),
    ("Sumapaz", "sumapaz", "upl"),
    ("Cuenca del Tunjuelo", "cuenca-del-tunjuelo", "upl"),
    ("Cerros Orientales", "cerros-orientales", "upl"),
]
ZONAS_MUNICIPIOS = [
    ("Soacha", "soacha", "municipio"), ("Sibate", "sibate", "municipio"),
    ("Mosquera", "mosquera", "municipio"), ("Madrid", "madrid", "municipio"),
    ("Funza", "funza", "municipio"), ("Facatativa", "facatativa", "municipio"),
    ("Bojaca", "bojaca", "municipio"), ("El Rosal", "el-rosal", "municipio"),
    ("Subachoque", "subachoque", "municipio"), ("Zipacon", "zipacon", "municipio"),
    ("Chia", "chia", "municipio"), ("Cajica", "cajica", "municipio"),
    ("Cota", "cota", "municipio"), ("Tabio", "tabio", "municipio"),
    ("Tenjo", "tenjo", "municipio"), ("Zipaquira", "zipaquira", "municipio"),
    ("Cogua", "cogua", "municipio"), ("Nemocon", "nemocon", "municipio"),
    ("Sopo", "sopo", "municipio"), ("Tocancipa", "tocancipa", "municipio"),
    ("Gachancipa", "gachancipa", "municipio"), ("Suesca", "suesca", "municipio"),
    ("Sesquile", "sesquile", "municipio"), ("Guatavita", "guatavita", "municipio"),
    ("Guasca", "guasca", "municipio"), ("La Calera", "la-calera", "municipio"),
]

GRUPOS = {
    "diario": ZONAS_DIARIO,
    "cada5": ZONAS_CADA5,
    "cada10": ZONAS_CADA10,
    "municipios": ZONAS_MUNICIPIOS,
}

OPERACIONES = ["venta", "arriendo"]
TIPOS = ["apartamento"]

# === Motor de FASES (norte -> comercial -> resto -> municipios) ===
TIPOS_RESIDENCIAL   = ["apartamento", "casa"]
TIPOS_COMERCIAL     = ["oficina", "bodega", "edificio", "local", "lote"]
TIPOS_MUN_COMERCIAL = ["lote", "bodega", "edificio", "local"]
PRIORIDAD_COMERCIAL = ["Puente Aranda", "Fontibon", "Barrios Unidos", "Teusaquillo", "Toberin"]   # F3: UPL NO-norte prioritarias
MUN_PRIORIDAD = ["Chia","Cajica","Cota","Tabio","Tenjo","Sopo","Tocancipa","Gachancipa",
                 "Zipaquira","Cogua","Nemocon","Sesquile","Suesca","Guatavita","Guasca",
                 "La Calera","Subachoque","El Rosal"]   # Sabana norte primero
BUSQUEDAS_POR_CORRIDA = 80    # unidades (barrio x tipo x operacion) por corrida ~= 16 min


# === Barrido POR BARRIO desde geo_model.json (cobertura por dias) ===
# Empieza por estas UPL (norte) y luego sigue con el resto, en tandas por corrida.
PRIORIDAD_UPL = ["Chapinero", "Usaquen", "Suba", "Rincon de Suba", "Niza", "Tibabuyes", "Britalia"]
BARRIOS_POR_CORRIDA = 40          # barrios por corrida (x2 operaciones ~= 44 min)
GEO_MODEL_PATHS = ["geo_model.json", "data/geo_model.json"]


def _slug(texto):
    t = unicodedata.normalize("NFD", str(texto))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _norm_upl(s):
    t = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").upper().strip()


def _cargar_geo():
    for ruta in GEO_MODEL_PATHS:
        fp = Path(ruta)
        if fp.exists():
            try:
                return json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None


def _barrios_ordenados():
    """Lista [(NombreBarrio, slug, 'barrio')] con las UPL de PRIORIDAD primero."""
    geo = _cargar_geo()
    if not geo:
        return []
    upl = geo.get("upl", {})
    orden, usados = [], set()
    def _add(v):
        for b in v.get("barrios", {}).keys():
            orden.append((b, _slug(b), "barrio"))
    prio_norm = [_norm_upl(x) for x in PRIORIDAD_UPL]
    for pn in prio_norm:
        for nombre_upl, v in upl.items():
            if _norm_upl(nombre_upl) == pn and nombre_upl not in usados:
                usados.add(nombre_upl); _add(v)
    for nombre_upl, v in upl.items():
        if nombre_upl not in usados:
            usados.add(nombre_upl); _add(v)
    return orden


def _cursor_barrios(base, guardar=None):
    fp = Path(base) / "cursor_barrios.json"
    idx = 0
    if fp.exists():
        try:
            idx = int(json.loads(fp.read_text(encoding="utf-8")).get("idx", 0))
        except Exception:
            idx = 0
    if guardar is not None:
        fp.write_text(json.dumps({"idx": guardar}), encoding="utf-8")
    return idx


def _zonas_barrios_hoy(base):
    """Devuelve la tanda de barrios de HOY y avanza el cursor (cobertura ciclica)."""
    orden = _barrios_ordenados()
    if not orden:
        return []
    n = BARRIOS_POR_CORRIDA
    chunks = max(1, math.ceil(len(orden) / n))
    idx = _cursor_barrios(base) % chunks
    tanda = orden[idx * n:(idx + 1) * n]
    _cursor_barrios(base, guardar=(idx + 1) % chunks)
    print("  barrios: tanda " + str(idx + 1) + "/" + str(chunks) + " (" + str(len(tanda)) + " barrios)")
    return tanda



def _plan_maestro(base):
    """Lista ordenada de trabajos (nombre, slug, origen, tipo, oper, fase) por fases."""
    geo = _cargar_geo()
    jobs = []
    if geo:
        upl = geo.get("upl", {})
        norte = []
        for pn in [_norm_upl(x) for x in PRIORIDAD_UPL]:
            for u, v in upl.items():
                if _norm_upl(u) == pn and u not in [x[0] for x in norte]:
                    norte.append((u, list(v.get("barrios", {}).keys())))
        norte_set = set(u for u, _ in norte)
        for u, barrios in norte:                       # F1: norte residencial
            for b in barrios:
                for tp in TIPOS_RESIDENCIAL:
                    for op in OPERACIONES:
                        jobs.append((b, _slug(b), "barrio", tp, op, "F1"))
        for u, barrios in norte:                       # F2: norte comercial
            for b in barrios:
                for tp in TIPOS_COMERCIAL:
                    for op in OPERACIONES:
                        jobs.append((b, _slug(b), "barrio", tp, op, "F2"))
        nonorte = []
        for pn in [_norm_upl(x) for x in PRIORIDAD_COMERCIAL]:
            for u, v in upl.items():
                if u not in norte_set and _norm_upl(u) == pn and u not in [x[0] for x in nonorte]:
                    nonorte.append((u, list(v.get("barrios", {}).keys())))
        for u, v in upl.items():
            if u not in norte_set and u not in [x[0] for x in nonorte]:
                nonorte.append((u, list(v.get("barrios", {}).keys())))
        for u, barrios in nonorte:                     # F3: no-norte comercial
            for b in barrios:
                for tp in TIPOS_COMERCIAL:
                    for op in OPERACIONES:
                        jobs.append((b, _slug(b), "barrio", tp, op, "F3"))
    mun = {n: sl for (n, sl, o) in ZONAS_MUNICIPIOS}
    mun_orden = []
    for n in MUN_PRIORIDAD:
        if n in mun and n not in [x[0] for x in mun_orden]:
            mun_orden.append((n, mun[n]))
    for (n, sl, o) in ZONAS_MUNICIPIOS:
        if n not in [x[0] for x in mun_orden]:
            mun_orden.append((n, sl))
    for n, sl in mun_orden:                            # F4a: municipios comercial
        for tp in TIPOS_MUN_COMERCIAL:
            for op in OPERACIONES:
                jobs.append((n, sl, "municipio", tp, op, "F4a"))
    for n, sl in mun_orden:                            # F4b: municipios residencial
        for tp in TIPOS_RESIDENCIAL:
            for op in OPERACIONES:
                jobs.append((n, sl, "municipio", tp, op, "F4b"))
    return jobs


def _plan_chunk(base):
    """Toma el bloque de HOY del plan maestro y avanza el cursor (ciclico)."""
    jobs = _plan_maestro(base)
    if not jobs:
        return []
    n = BUSQUEDAS_POR_CORRIDA
    chunks = max(1, math.ceil(len(jobs) / n))
    idx = _cursor_barrios(base) % chunks
    sub = jobs[idx * n:(idx + 1) * n]
    _cursor_barrios(base, guardar=(idx + 1) % chunks)
    fases = []
    for j in sub:
        if j[5] not in fases:
            fases.append(j[5])
    print("  plan: bloque " + str(idx + 1) + "/" + str(chunks)
          + " | fase(s) " + ",".join(fases) + " | " + str(len(sub)) + " busquedas")
    return [(j[0], j[1], j[2], [j[3]], [j[4]]) for j in sub]


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
    anchor = html.find("initialResults")
    if anchor < 0:
        return []
    rk = html.find("results", anchor)
    if rk < 0:
        return []
    br = html.find("[", rk)
    if br < 0:
        return []
    depth = 0
    i = br
    end = -1
    while i < len(html):
        ch = html[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end < 0:
        return []
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
    if not results:
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
            "tipo_portal": (r.get("mtipoinmueble") or {}).get("nombre"),
            "fecha_pub": None,
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
            "tipo_portal": (r.get("property_type") or {}).get("name"),
            "fecha_pub": r.get("created_at"),
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
            "tipoPortal": g("tipo_portal"),
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
            "fechaPublicacion": g("fecha_pub"),
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


def publicar(carpeta="data", grupo="diario"):
    """Rastrea las zonas del GRUPO. Escribe: un JSON por zona, un consolidado
    por grupo, index.json (manifiesto), tipos.json (inventario de tipos por
    portal) e historial.json (variacion de conteos entre corridas + tiempos)."""
    base = Path(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    if grupo == "barrios":
        zonas = _plan_chunk(base)
        if not zonas:
            print("  (falta geo_model.json en el repo: no hay barrios que rastrear)")
    else:
        zonas = GRUPOS.get(grupo, ZONAS_DIARIO)
    generado = datetime.now()
    MES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
    stamp = generado.strftime("%Y.") + MES[generado.month - 1] + generado.strftime(".%d %H:%M")

    datasets = []
    consolidado = []
    tipos = {}         # tipos[portal][nombre_tipo] = conteo
    tiempos = []       # medicion por zona
    portal = "metrocuadrado"

    for entry in zonas:
        if len(entry) == 5:
            nombre, slug, origen, _tset, _oset = entry
        else:
            nombre, slug, origen = entry
            _tset, _oset = TIPOS, OPERACIONES
        ciudad = slug if origen == "municipio" else CIUDAD_POR_DEFECTO
        zona = "" if origen == "municipio" else slug
        for oper in _oset:
            for tipo in _tset:
                etiqueta = oper.capitalize() + " - " + tipo.capitalize() + " - " + nombre
                clave = oper + "_" + tipo + "_" + slug
                print("\n== " + etiqueta + " (" + origen + ") ==")
                t0 = time.time()
                try:
                    filas = scrape_portal(portal, oper, tipo, zona, ciudad, PAGINAS_POR_DEFECTO)
                    df = pd.DataFrame(filas)
                    inmuebles = _df_a_contrato(df, portal, oper, tipo) if not df.empty else []
                    # inventario de tipos (lo que realmente devolvio el portal)
                    if not df.empty and "tipo_portal" in df:
                        for tp in df["tipo_portal"].dropna():
                            tipos.setdefault(portal, {})
                            tipos[portal][tp] = tipos[portal].get(tp, 0) + 1
                except Exception as e:
                    print("  aviso: " + str(e))
                    inmuebles = []
                dt = round(time.time() - t0, 1)
                # enriquecer cada inmueble con zona/origen/operacion
                for it in inmuebles:
                    it["zonaConsulta"] = nombre
                    it["zonaSlug"] = slug
                    it["origenZona"] = origen
                archivo = clave + ".json"
                (base / archivo).write_text(json.dumps(
                    {"ok": True, "total": len(inmuebles), "zona": nombre, "origen": origen,
                     "operacion": oper, "tipo": tipo, "generado": stamp, "inmuebles": inmuebles},
                    ensure_ascii=False, indent=2), encoding="utf-8")
                consolidado.extend(inmuebles)
                datasets.append({"clave": clave, "etiqueta": etiqueta, "archivo": archivo,
                                 "total": len(inmuebles), "operacion": oper, "tipo": tipo,
                                 "zona": nombre, "slug": slug, "origen": origen, "segundos": dt})
                tiempos.append({"zona": nombre, "operacion": oper, "total": len(inmuebles), "segundos": dt})
                print("  " + str(len(inmuebles)) + " inmueble(s) en " + str(dt) + "s -> " + archivo)

    if grupo == "barrios":
        por_tipo = {}
        for d in datasets:
            r = por_tipo.setdefault(d["tipo"], {"n": 0, "cero": 0})
            r["n"] += 1
            if d["total"] == 0:
                r["cero"] += 1
        ceros = sum(1 for d in datasets if d["total"] == 0)
        alertas = []
        for tp, r in por_tipo.items():
            if r["n"] >= 5 and r["cero"] == r["n"]:
                alertas.append("tipo '" + tp + "' dio 0 en las " + str(r["n"]) + " busquedas del bloque (revisar slug/tipo)")
        aud = {"generado": stamp, "busquedas": len(datasets), "con_cero": ceros,
               "por_tipo": por_tipo, "alertas": alertas}
        (base / "auditoria.json").write_text(json.dumps(aud, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n#### AUDITOR ####")
        print("  busquedas: " + str(len(datasets)) + " | con 0 resultados: " + str(ceros))
        for a in alertas:
            print("  ALERTA: " + a)

    # consolidado del grupo (lo que la app carga de una)
    cons_archivo = "consolidado_" + grupo + ".json"
    (base / cons_archivo).write_text(json.dumps(
        {"ok": True, "grupo": grupo, "total": len(consolidado), "generado": stamp,
         "inmuebles": consolidado}, ensure_ascii=False, indent=2), encoding="utf-8")

    # noticias (solo en el grupo diario, para no repetir)
    noticias_meta = None
    if PUBLICAR_NOTICIAS and grupo == "diario":
        try:
            items = leer_noticias()
        except Exception as e:
            print("  aviso noticias: " + str(e)); items = []
        noticias = [{"titulo": it.get("titular", ""), "fuente": it.get("medio", ""),
                     "fecha": generado.strftime("%Y-%m-%d"), "resumen": "",
                     "url": it.get("url", "")} for it in items]
        (base / "noticias.json").write_text(json.dumps({"noticias": noticias},
            ensure_ascii=False, indent=2), encoding="utf-8")
        noticias_meta = {"archivo": "noticias.json", "total": len(noticias)}

    # tipos.json (inventario acumulado por portal; fusiona con lo previo)
    tipos_path = base / "tipos.json"
    prev_tipos = {}
    if tipos_path.exists():
        try:
            prev_tipos = json.loads(tipos_path.read_text(encoding="utf-8")).get("tipos", {})
        except Exception:
            prev_tipos = {}
    for pt, d in tipos.items():
        prev_tipos.setdefault(pt, {})
        for k, v in d.items():
            prev_tipos[pt][k] = v  # ultimo conteo observado
    tipos_path.write_text(json.dumps({"generado": stamp, "tipos": prev_tipos},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # historial.json (una entrada por corrida: totales por zona + tiempos)
    hist_path = base / "historial.json"
    historial = []
    if hist_path.exists():
        try:
            historial = json.loads(hist_path.read_text(encoding="utf-8"))
            if not isinstance(historial, list):
                historial = []
        except Exception:
            historial = []
    # variacion vs corrida anterior del mismo grupo
    prev = None
    for h in reversed(historial):
        if h.get("grupo") == grupo:
            prev = h; break
    variaciones = {}
    if prev:
        for d in datasets:
            antes = next((x["total"] for x in prev.get("datasets", []) if x["clave"] == d["clave"]), None)
            if antes is not None:
                variaciones[d["clave"]] = d["total"] - antes
    historial.append({
        "grupo": grupo, "generado": stamp, "iso": generado.isoformat(timespec="seconds"),
        "total": len(consolidado), "segundos_total": round(sum(t["segundos"] for t in tiempos), 1),
        "datasets": [{"clave": d["clave"], "total": d["total"], "segundos": d["segundos"]} for d in datasets],
        "variaciones": variaciones,
    })
    if len(historial) > 500:
        historial = historial[-500:]
    hist_path.write_text(json.dumps(historial, ensure_ascii=False, indent=2), encoding="utf-8")

    # index.json (manifiesto: fusiona datasets de todos los grupos ya publicados)
    idx_path = base / "index.json"
    all_ds = {}
    if idx_path.exists():
        try:
            for d in json.loads(idx_path.read_text(encoding="utf-8")).get("datasets", []):
                all_ds[d["clave"]] = d
        except Exception:
            pass
    for d in datasets:
        all_ds[d["clave"]] = d
    manifiesto = {
        "generado": generado.isoformat(timespec="seconds"),
        "generado_humano": stamp,
        "grupo_actual": grupo,
        "ciudad": CIUDAD_POR_DEFECTO,
        "datasets": list(all_ds.values()),
        "consolidados": {"diario": "consolidado_diario.json", "cada5": "consolidado_cada5.json",
                         "cada10": "consolidado_cada10.json", "municipios": "consolidado_municipios.json"},
        "tipos": "tipos.json",
        "historial": "historial.json",
        "noticias": noticias_meta,
    }
    idx_path.write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n== RESUMEN GRUPO " + grupo.upper() + " ==")
    print("  zonas: " + str(len(zonas)) + " | inmuebles: " + str(len(consolidado)))
    print("  tiempo total: " + str(round(sum(t["segundos"] for t in tiempos), 1)) + "s")
    print("  ultima corrida: " + stamp)
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
    p1.add_argument("--grupo", default="diario")
    p2 = sub.add_parser("diagnostico")
    p2.add_argument("--carpeta", default="data")
    args = parser.parse_args()
    if args.cmd == "doctor":
        doctor()
    elif args.cmd == "publicar":
        publicar(args.carpeta, args.grupo)
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

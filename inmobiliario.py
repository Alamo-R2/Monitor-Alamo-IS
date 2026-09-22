#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MONITOR INMOBILIARIO — Opción B. Comandos: buscar avaluo noticias doctor publicar diagnostico"""
import argparse
import json
import re
import sys
import time
import math
import random
import hashlib
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
        "url": "https://www.fincaraiz.com.co/{operacion}/{tipo}/{zona}/{ciudad}?pagina={pagina}",
        "css_tarjeta": "article", "css_precio": "[class*='price']",
        "css_titulo": "h2", "css_area": "[class*='area']",
        "css_hab": "[class*='room']", "css_ubic": "[class*='location']",
    },
    "ciencuadras": {
        "url": "https://www.ciencuadras.com/{operacion}/{ciudad}/{ciudad}/{zona}/{tipo}",
        "css_tarjeta": "a[href*='/inmueble/']", "css_precio": "",
        "css_titulo": "", "css_area": "", "css_hab": "", "css_ubic": "",
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
TIPO_FR = {"apartamento":"apartamentos","casa":"casas","oficina":"oficinas","bodega":"bodegas","local":"locales","lote":"lotes"}


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


# === v2 · Enriquecimiento geográfico y saneo $/m² (para que las 3 fuentes se alineen en la app) ===
# Bandas de $/m² plausibles (idénticas a las de 5a en la app). Fuera de banda = error de
# digitación del aviso -> se descarta en el monitor para no contaminar el pool/5c.
PPM2_BANDAS = {"venta": (300000, 50000000), "arriendo": (500, 700000)}

def _nk(s):
    """Normaliza un nombre (barrio/UPL): sin tildes, MAYÚSCULAS, no-alfanumérico -> espacio."""
    t = unicodedata.normalize("NFD", str(s if s is not None else ""))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").upper()
    t = re.sub(r"[^A-Z0-9]+", " ", t).strip()
    return re.sub(r"\s+", " ", t)

_GEO_IDX = None
def _geo_idx():
    """Devuelve (barrio_norm -> (UPL, localidad), uplname_norm -> (UPL, localidad)) desde geo_model."""
    global _GEO_IDX
    if _GEO_IDX is not None:
        return _GEO_IDX
    geo = _cargar_geo() or {}
    barrio2, uplname2 = {}, {}
    for uplname, v in (geo.get("upl") or {}).items():
        if not isinstance(v, dict):
            continue
        loc = v.get("localidad") or ""
        uplname2.setdefault(_nk(uplname), (uplname, loc))
        for b in (v.get("barrios") or {}).keys():
            barrio2.setdefault(_nk(b), (uplname, loc))  # primer match gana (barrios homónimos entre UPL)
    _GEO_IDX = (barrio2, uplname2)
    return _GEO_IDX

def _upl_loc_de(nombre):
    """UPL y localidad para un nombre que puede ser un barrio específico o un nombre de UPL/localidad."""
    b2, u2 = _geo_idx()
    k = _nk(nombre)
    if not k:
        return ("", "")
    if k in b2:
        return b2[k]
    if k in u2:
        return u2[k]
    return ("", "")

def _es_barrio_especifico(s):
    b2, _u = _geo_idx()
    return _nk(s) in b2

def _ppm2_ok(precio, area, operacion):
    """True si el $/m² cae en banda plausible (o si no hay datos para juzgar)."""
    try:
        p = float(precio); a = float(area)
    except (TypeError, ValueError):
        return True
    if not (p > 0 and a > 0):
        return True
    ppm = p / a
    banda = PPM2_BANDAS.get(str(operacion).lower())
    if not banda:
        return True
    return banda[0] <= ppm <= banda[1]


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


def _cursor_barrios(base, guardar=None, name="cursor_barrios.json"):
    fp = Path(base) / name
    idx = 0
    if fp.exists():
        try:
            idx = int(json.loads(fp.read_text(encoding="utf-8")).get("idx", 0))
        except Exception:
            idx = 0
    if guardar is not None:
        fp.write_text(json.dumps({"idx": guardar}), encoding="utf-8")
    return idx


def _zonas_barrios_hoy(base, suffix="", n=None):
    """Devuelve la tanda de barrios de HOY y avanza el cursor (cobertura ciclica). Cursor propio por 'suffix' (portal)."""
    orden = _barrios_ordenados()
    if not orden:
        return []
    n = n or BARRIOS_POR_CORRIDA
    cname = "cursor_barrios" + suffix + ".json"
    chunks = max(1, math.ceil(len(orden) / n))
    idx = _cursor_barrios(base, name=cname) % chunks
    tanda = orden[idx * n:(idx + 1) * n]
    _cursor_barrios(base, guardar=(idx + 1) % chunks, name=cname)
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


def _estrato_ok(v):
    try:
        n = int(float(v)); return n if 1 <= n <= 6 else None
    except Exception:
        return None


def _anio_ok(v):
    try:
        n = int(float(v)); return n if 1900 <= n <= 2035 else None
    except Exception:
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
            "estrato": _estrato_ok(r.get("estrato")),
            "antiguedad": None,
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
        ciudad_it = ""
        for _c in (loc.get("city"), loc.get("location_secondary"), loc.get("location_city")):
            if isinstance(_c, dict):
                _c = _c.get("name")
            if _c:
                ciudad_it = _c
                break
        if not ciudad_it:
            ciudad_it = r.get("title") or ""
        link = r.get("link")
        filas.append({
            "titulo": r.get("title"),
            "precio": _num(precio),
            "area_m2": _dec(r.get("m2") or r.get("m2Built") or r.get("m2apto")),
            "habitaciones": _num(r.get("bedrooms")),
            "banos": _num(r.get("bathrooms")),
            "parqueaderos": _num(r.get("garage")),
            "administracion": _num(admin) if admin else None,
            "estrato": _estrato_ok(r.get("stratum")),
            "antiguedad": _anio_ok(r.get("construction_year")),
            "ubicacion": barrio,
            "ciudad_item": ciudad_it,
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


def _desde_ciencuadras(page):
    """Ciencuadras es SSR: cada aviso es un <a href='/inmueble/...-{id}'> con el texto
    completo (tipo, barrio, area, hab, banos, garajes, precio). Se parsea por regex sobre
    el texto del ancla + el id del href. No expone lat/lon por aviso."""
    filas = []
    vistos = set()
    for a in page.query_selector_all("a[href*='/inmueble/']"):
        href = a.get_attribute("href") or ""
        mid = re.search(r"-(\d+)/?$", href)
        pid = mid.group(1) if mid else None
        if not pid or pid in vistos:
            continue
        try:
            txt = (a.inner_text() or "").replace("\n", " ")
        except Exception:
            txt = ""
        if "m2" not in txt and "$" not in txt:
            continue
        vistos.add(pid)
        def rx(pat):
            m = re.search(pat, txt, re.I)
            return m.group(1) if m else None
        precio = rx(r"\$\s*([\d][\d.,]*)")
        area = rx(r"([\d][\d.,]*)\s*m2")
        hab = rx(r"Habit\w*\.?\s*(\d+)")
        ban = rx(r"Ba[\u00f1n]os?\s*(\d+)")
        gar = rx(r"Garaj\w*\s*(\d+)")
        tipo_p = rx(r"([A-Za-z\u00c0-\u017f]+)\s+en\s+(?:venta|arriendo)")
        barrio = rx(r"Bogot[\u00e1a]\s*,[^,]*,\s*(.+?)\s+[\d][\d.,]*\s*m2")
        if not barrio:
            barrio = rx(r"Bogot[\u00e1a]\s*,[^,]*,\s*([^,]+)")
        if not barrio:  # respaldo: barrio desde el slug de la URL
            mb = re.search(r"-en-(?:venta|arriendo)-en-(.+?)-bogota-\d+", href, re.I)
            if mb:
                barrio = mb.group(1).replace("-", " ").title()
        link = ("https://www.ciencuadras.com" + href) if href.startswith("/") else href
        filas.append({
            "titulo": (tipo_p + " en " + (barrio or "")) if tipo_p else None,
            "precio": _num(precio),
            "area_m2": _dec(area),
            "habitaciones": _num(hab),
            "banos": _num(ban),
            "parqueaderos": _num(gar),
            "administracion": None,
            "ubicacion": barrio,
            "ciudad_item": "",
            "url": link,
            "id_domus": pid,
            "tipo_portal": tipo_p,
            "fecha_pub": None,
            "lat": None,
            "lon": None,
            "location_type": "aproximada",
            "_fuente": "ciencuadras-dom",
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
    for estrategia in (_desde_metrocuadrado, _desde_fincaraiz, _desde_ciencuadras):
        filas = estrategia(page)
        if _validar(filas)[0]:
            return filas
    return _desde_css(page, cfg)


def scrape_portal(portal, operacion, tipo, zona, ciudad, paginas):
    cfg = PORTALES[portal]
    tipo_url = TIPO_FR.get(tipo, tipo) if portal == "fincaraiz" else tipo
    todos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for n in range(1, paginas + 1):
            url = cfg["url"].format(operacion=operacion, tipo=tipo_url, zona=zona, ciudad=ciudad, pagina=n)
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
    if portal == "fincaraiz":
        ck = _slug(ciudad)
        def _txt(v):
            if isinstance(v, list):
                return " ".join(str(x) for x in v)
            return str(v) if v is not None else ""
        def _ok(f):
            base = _slug(_txt(f.get("ciudad_item")) + " " + _txt(f.get("titulo")))
            return ck in base
        antes = len(unicos)
        unicos = [f for f in unicos if _ok(f)]
        if antes != len(unicos):
            print("    fincaraiz: descartados por ciudad != " + ciudad + ": " + str(antes - len(unicos)))
    if portal == "ciencuadras":
        zbarrio = zona.replace("-", " ").upper()  # avisos sin barrio propio (nivel ciudad) -> barrio consultado
        for f in unicos:
            u = (f.get("ubicacion") or "").strip()
            if not u or u.lower() in ("bogota", "bogot\u00e1"):
                f["ubicacion"] = zbarrio
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
    descartados_ppm2 = 0
    for idx, r in df.reset_index(drop=True).iterrows():
        def g(k):
            v = r.get(k)
            return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
        precio = g("precio"); area = g("area_m2")
        # Saneo $/m²: descarta atípicos (errores de digitación) para no contaminar el pool/5c
        if not _ppm2_ok(precio, area, operacion):
            descartados_ppm2 += 1
            continue
        barrio = (str(g("ubicacion")).upper() if g("ubicacion") else "")
        upl, _loc = _upl_loc_de(barrio)
        try:
            ppm2 = round(float(precio) / float(area)) if (precio and area and float(area) > 0) else None
        except (TypeError, ValueError):
            ppm2 = None
        inmuebles.append({
            "id": "MI-" + str(idx + 1),
            "operacion": [oper],
            "tipo": tipo,
            "tipoPortal": g("tipo_portal"),
            "precio": precio,
            "area": area,
            "precioM2": ppm2,
            "administracion": g("administracion"),
            "barrio": barrio,
            "upl": upl,
            "ciudad": "Bogotá",
            "direccion": "",
            "habitaciones": g("habitaciones"),
            "banos": g("banos"),
            "parqueaderos": g("parqueaderos"),
            "estrato": g("estrato"),
            "antiguedad": g("antiguedad"),
            "portalNombre": portal,
            "sourceLink": g("url"),
            "titulo": g("titulo"),
            "id_domus": g("id_domus"),
            "fechaPublicacion": g("fecha_pub"),
            "lat": g("lat"),
            "lon": g("lon"),
            "location_type": g("location_type") or "aproximada",
        })
    if descartados_ppm2:
        print("    saneo $/m2: " + str(descartados_ppm2) + " aviso(s) fuera de banda descartados")
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


def publicar(carpeta="data", grupo="diario", portal="metrocuadrado", tipos_filtro=None, cursor_suffix="", barrios_n=None):
    """Rastrea las zonas del GRUPO. Escribe: un JSON por zona, un consolidado
    por grupo, index.json (manifiesto), tipos.json (inventario de tipos por
    portal) e historial.json (variacion de conteos entre corridas + tiempos)."""
    base = Path(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    if grupo == "barrios":
        zonas = _plan_chunk(base)
        if not zonas:
            print("  (falta geo_model.json en el repo: no hay barrios que rastrear)")
    elif grupo == "barrios_res":
        zonas = _zonas_barrios_hoy(base, cursor_suffix, barrios_n)
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
    portal = portal or "metrocuadrado"   # viene por parametro (default metrocuadrado)
    pfx = "" if portal == "metrocuadrado" else portal + "_"   # prefijo de clave/archivo para no chocar con metro
    if pfx:  # limpia artefactos mal nombrados de versiones previas (portal repetido en la clave)
        _badpat = re.compile(r"^" + re.escape(portal) + r"_(venta|arriendo)_" + re.escape(portal) + r"_")
        import glob as _glob
        for _f in _glob.glob(str(base / (portal + "_*.json"))):
            if _badpat.match(Path(_f).name):
                try:
                    Path(_f).unlink()
                except Exception:
                    pass

    for entry in zonas:
        if len(entry) == 5:
            nombre, slug, origen, _tset, _oset = entry
        else:
            nombre, slug, origen = entry
            _tset, _oset = (tipos_filtro or TIPOS), OPERACIONES
        ciudad = slug if origen == "municipio" else CIUDAD_POR_DEFECTO
        zona = "" if origen == "municipio" else slug
        for oper in _oset:
            for tipo in _tset:
                etiqueta = oper.capitalize() + " - " + tipo.capitalize() + " - " + nombre
                clave = pfx + oper + "_" + tipo + "_" + slug
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
                    if origen == "municipio":
                        it["ciudad"] = nombre            # municipios: sin UPL/barrio del modelo de Bogotá
                    else:
                        it["ciudad"] = "Bogotá"
                        _upl, _loc = _upl_loc_de(nombre)  # barrio consultado = UPL determinista
                        if _upl:
                            it["upl"] = _upl
                        # Si la fuente trae el barrio grueso (localidad/UPL) o vacío, usar el barrio
                        # consultado (específico) para que 5c agrupe bien las 3 fuentes.
                        _b = (it.get("barrio") or "").strip()
                        if (not _b) or (not _es_barrio_especifico(_b)):
                            it["barrio"] = str(nombre).upper()
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
    cons_archivo = "consolidado_" + pfx + grupo + ".json"
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
    if pfx:  # quita del manifiesto las claves stale del mismo patron buggy (portal repetido)
        _badpat = re.compile(r"^" + re.escape(portal) + r"_(venta|arriendo)_" + re.escape(portal) + r"_")
        all_ds = {k: v for k, v in all_ds.items() if not _badpat.match(k)}
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


# === v3 · Enriquecimiento de CONTACTOS (portal-agnóstico, bajo demanda, anti-bloqueo) ===
# Estrategia: cola alimentada por las fichas del avalúo -> se visita cada ficha como
# navegador real, con pausas largas aleatorias, intervalo por dominio, revalidación
# espaciada y backoff ante 403/429/captcha. Se acumula en data/contactos.json con hash e
# historial para VERIFICAR si el contacto cambia entre revisiones (nuevo/estable/cambiado).
CONTACTO_MAX_POR_CORRIDA = 12          # fichas por corrida (bajo, para no disparar flags)
CONTACTO_PAUSA = (8, 20)               # seg, pausa aleatoria entre fichas
CONTACTO_REVALIDAR_DIAS = 30           # no re-visitar una ficha vista hace < N días
CONTACTO_MIN_INTERVALO_DOM = 6         # seg mínimo entre golpes al mismo dominio
CONTACTO_BLOQUEO_MARKERS = ("captcha", "unusual traffic", "access denied",
                            "request blocked", "are you a human", "cf-challenge",
                            "verify you are human", "px-captcha")

_RE_TEL_CO = re.compile(r'(?:\+?57[\s.\-]?)?(3\d{2})[\s.\-]?(\d{3})[\s.\-]?(\d{4})')
_RE_EMAIL  = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
_RE_WA     = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=)(?:57)?(3\d{9})', re.I)
_RE_JSONLD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
_RE_PLACEHOLDER = re.compile(r'placeholder\s*=\s*"[^"]*"|value\s*=\s*"[^"]*"', re.I)
_RE_EJEMPLO = re.compile(r'(?:ej\.?|ejemplo)\s*:?\s*\+?57?\s*3\d[\d\s.\-]{7,}', re.I)
_RE_AGENCIA = re.compile(r'((?:[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][A-Za-z\u00c0-\u017f&.\s]{1,48}?)?(?i:inmobiliari[ao]s?|inmuebles|inversiones|bienes\s+ra[i\u00ed]ces|propiedad\s+ra[i\u00ed]z|constructora|realty)[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1&.\s]{0,20})')
_RE_NEXTDATA = re.compile(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.I | re.S)
_PORTAL_MAILDOM = ('fincaraiz', 'metrocuadrado', 'ciencuadras')

def _tel_norm(s):
    if not s: return None
    m = _RE_TEL_CO.search(str(s))
    return ("+57" + m.group(1) + m.group(2) + m.group(3)) if m else None

def _jsonld_contacto(html, out):
    """Extrae telephone/email/nombre-agencia de bloques JSON-LD según @type."""
    for blob in _RE_JSONLD.findall(html or ""):
        try:
            data = json.loads(blob.strip())
        except Exception:
            continue
        pila = [data]
        while pila:
            o = pila.pop()
            if isinstance(o, list):
                pila.extend(o); continue
            if not isinstance(o, dict):
                continue
            tipo = str(o.get("@type") or "").lower()
            if not out["telefono"] and o.get("telephone"):
                out["telefono"] = _tel_norm(o.get("telephone")) or out["telefono"]
            if not out["email"] and isinstance(o.get("email"), str):
                out["email"] = o.get("email").strip() or out["email"]
            if o.get("name") and any(t in tipo for t in ("realestateagent", "organization", "person", "localbusiness")):
                if not out["inmobiliaria"]:
                    out["inmobiliaria"] = str(o.get("name")).strip()
            for v in o.values():
                if isinstance(v, (dict, list)):
                    pila.append(v)

def _nextdata_contacto(html, out):
    """Muchos portales (Next.js) embeben datos en <script id=__NEXT_DATA__>. Se toma
    telefono/email/agencia SOLO si traen valor válido; se descartan correos del propio portal."""
    m = _RE_NEXTDATA.search(html or "")
    if not m:
        return
    try:
        data = json.loads(m.group(1))
    except Exception:
        return
    pila = [data]
    while pila:
        o = pila.pop()
        if isinstance(o, list):
            pila.extend(o); continue
        if not isinstance(o, dict):
            continue
        for k, v in o.items():
            kl = str(k).lower()
            if isinstance(v, (str, int)):
                sv = str(v)
                if not out["telefono"] and any(t in kl for t in ("phone", "mobile", "celular", "whatsapp", "telefono")):
                    tn = _tel_norm(sv)
                    if tn: out["telefono"] = tn
                elif not out["email"] and ("email" in kl or "correo" in kl):
                    if "@" in sv and not any(d in sv.lower() for d in _PORTAL_MAILDOM):
                        out["email"] = sv.strip()
                elif not out["inmobiliaria"] and any(t in kl for t in ("inmobiliaria", "companyname", "realtor", "publishername", "agencyname")):
                    if 2 < len(sv) < 60: out["inmobiliaria"] = sv.strip()
            elif isinstance(v, (dict, list)):
                pila.append(v)


def extraer_contacto(html):
    """Portal-agnóstico y CONSERVADOR: teléfono/email solo desde señales confiables
    (tel:/mailto:/wa.me/JSON-LD) o de la descripción del anunciante; nunca de números
    sueltos ni de placeholders/ejemplos de formularios. La inmobiliaria (agencia) se
    captura del texto visible. Calibrado contra Metrocuadrado (tel. tras formulario)."""
    out = {"nombre": None, "telefono": None, "email": None, "inmobiliaria": None}
    h = html or ""
    # 1) anclas confiables tel: / mailto: / WhatsApp
    m = re.search(r'href=["\']tel:([^"\']+)', h, re.I)
    if m: out["telefono"] = _tel_norm(m.group(1))
    m = re.search(r'href=["\']mailto:([^"\'?]+)', h, re.I)
    if m: out["email"] = m.group(1).strip()
    if not out["telefono"]:
        m = _RE_WA.search(h)
        if m: out["telefono"] = "+57" + m.group(1)
    # 2) JSON-LD (@type agente/organización)
    _jsonld_contacto(h, out)
    _nextdata_contacto(h, out)
    # texto sin etiquetas, sin placeholders/valores de inputs ni "Ej.: ..." (evita el número de ejemplo)
    sin_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", h, flags=re.I | re.S)
    limpio = _RE_PLACEHOLDER.sub(" ", sin_scripts)
    limpio = _RE_EJEMPLO.sub(" ", limpio)
    texto = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", limpio))
    # 3) inmobiliaria / agencia desde texto visible
    if not out["inmobiliaria"]:
        ma = _RE_AGENCIA.search(texto)
        if ma:
            ag = re.sub(r"\s+", " ", ma.group(1)).strip()
            ag = re.sub(r"\s+(?:Llamar|Contactar|WhatsApp|Correo|Ver|Compartir|Mapa|Galer[i\u00ed]a|Favorito|Reportar|Tel[e\u00e9]fono|Email).*$", "", ag, flags=re.I).strip()
            ag = re.sub(r"\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1]$", "", ag).strip()
            out["inmobiliaria"] = ag[:60]
    # 4) email por regex si aún falta
    if not out["email"]:
        me = _RE_EMAIL.search(texto)
        if me and not any(d in me.group(0).lower() for d in _PORTAL_MAILDOM):
            out["email"] = me.group(0)
    # 5) teléfono de respaldo SOLO si el anunciante lo escribió en la descripción
    #    (frases de contacto reales); NUNCA desde el botón "Contactar" ni números sueltos.
    if not out["telefono"]:
        low = texto.lower()
        for kw in ("informes", "whatsapp", "celular", "comun\u00edcate", "comunicate",
                   "ll\u00e1manos", "llamanos", "contacto directo", "cel:"):
            i = low.find(kw)
            if i >= 0:
                mm = _RE_TEL_CO.search(texto[i:i + 120])
                if mm:
                    out["telefono"] = "+57" + mm.group(1) + mm.group(2) + mm.group(3); break
    return out

def _ck(url):
    return (str(url or "").split("?")[0].split("#")[0]).strip().lower()

def _dom(url):
    m = re.search(r'https?://([^/]+)', str(url or ""))
    return (m.group(1).lower() if m else "")

def _hash_contacto(c):
    base = "|".join([(c.get("nombre") or ""), (c.get("telefono") or ""),
                     (c.get("email") or ""), (c.get("inmobiliaria") or "")])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

def _cargar_json(fp, default):
    try:
        return json.loads(Path(fp).read_text(encoding="utf-8"))
    except Exception:
        return default

def enriquecer_contactos(base="data", maxn=None):
    """Procesa la cola (data/contactos_cola.json) + revalidación espaciada y acumula en
    data/contactos.json con hash e historial. Devuelve un resumen."""
    maxn = maxn or CONTACTO_MAX_POR_CORRIDA
    base = Path(base)
    store = _cargar_json(base / "contactos.json", {})           # {clave: {...}}
    cola  = _cargar_json(base / "contactos_cola.json", [])       # [enlace, ...] o [{"sourceLink":..}]
    cola_urls = []
    for x in cola:
        u = x.get("sourceLink") if isinstance(x, dict) else x
        if u: cola_urls.append(u)
    hoy = datetime.now()
    def _vencido(k):
        v = store.get(k) or {}
        ls = v.get("last_seen")
        if not ls: return True
        try:
            return (hoy - datetime.strptime(ls[:10], "%Y-%m-%d")).days >= CONTACTO_REVALIDAR_DIAS
        except Exception:
            return True
    # worklist: primero la cola (no vista o vencida), luego revalidación de las más antiguas
    work, vistos = [], set()
    for u in cola_urls:
        k = _ck(u)
        if k in vistos: continue
        vistos.add(k)
        if _vencido(k): work.append(u)
        if len(work) >= maxn: break
    if len(work) < maxn:
        antiguos = sorted([kk for kk in store.keys() if _vencido(kk)],
                          key=lambda kk: (store[kk].get("last_seen") or ""))
        for kk in antiguos:
            u = store[kk].get("sourceLink") or kk
            if _ck(u) in vistos: continue
            vistos.add(_ck(u)); work.append(u)
            if len(work) >= maxn: break

    nuevos = estables = cambiados = fallidos = 0
    if work:
        try:
            from playwright.sync_api import sync_playwright  # import local (solo si hay trabajo)
        except Exception:
            print("  (sin playwright: no se puede enriquecer contactos)"); return {"error": "sin_playwright"}
        ultimo_dom, bloqueados = {}, set()
        random.shuffle(work)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for u in work:
                dom = _dom(u)
                if dom in bloqueados:
                    continue
                # intervalo mínimo por dominio
                dt = time.time() - ultimo_dom.get(dom, 0)
                if dt < CONTACTO_MIN_INTERVALO_DOM:
                    time.sleep(CONTACTO_MIN_INTERVALO_DOM - dt)
                try:
                    page = _abrir_pagina(browser, u)
                    html = page.content()
                except Exception as e:
                    print("    aviso ficha: " + str(e)); fallidos += 1
                    ultimo_dom[dom] = time.time()
                    time.sleep(random.uniform(*CONTACTO_PAUSA)); continue
                ultimo_dom[dom] = time.time()
                low = (html or "").lower()
                if any(mk in low for mk in CONTACTO_BLOQUEO_MARKERS):
                    print("    BLOQUEO detectado en " + dom + " -> se detiene ese dominio esta corrida")
                    bloqueados.add(dom); fallidos += 1
                    time.sleep(random.uniform(*CONTACTO_PAUSA)); continue
                c = extraer_contacto(html)
                if not (c.get("telefono") or c.get("email") or c.get("inmobiliaria")):
                    fallidos += 1
                    time.sleep(random.uniform(*CONTACTO_PAUSA)); continue
                k = _ck(u); hsh = _hash_contacto(c); fstamp = hoy.strftime("%Y-%m-%d")
                prev = store.get(k)
                if not prev:
                    store[k] = {"sourceLink": u, "nombre": c["nombre"], "telefono": c["telefono"],
                                "email": c["email"], "inmobiliaria": c["inmobiliaria"], "fuente": dom,
                                "first_seen": fstamp, "last_seen": fstamp, "revisiones": 1,
                                "hash": hsh, "historial": []}
                    nuevos += 1
                elif prev.get("hash") == hsh:
                    prev["last_seen"] = fstamp; prev["revisiones"] = prev.get("revisiones", 1) + 1
                    estables += 1
                else:
                    prev.setdefault("historial", []).append(
                        {"fecha": prev.get("last_seen"), "hash": prev.get("hash"),
                         "telefono": prev.get("telefono"), "email": prev.get("email"),
                         "inmobiliaria": prev.get("inmobiliaria")})
                    prev.update({"nombre": c["nombre"], "telefono": c["telefono"], "email": c["email"],
                                 "inmobiliaria": c["inmobiliaria"], "last_seen": fstamp,
                                 "hash": hsh, "cambio_ultimo": fstamp})
                    prev["revisiones"] = prev.get("revisiones", 1) + 1
                    cambiados += 1
                time.sleep(random.uniform(*CONTACTO_PAUSA))
            browser.close()

    # persistir: quitar de la cola lo procesado
    procesados = {_ck(u) for u in work}
    nueva_cola = [u for u in cola_urls if _ck(u) not in procesados]
    (base / "contactos.json").write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    (base / "contactos_cola.json").write_text(json.dumps(nueva_cola, ensure_ascii=False, indent=2), encoding="utf-8")
    resumen = {"generado": hoy.strftime("%Y-%m-%d %H:%M"), "procesados": len(work),
               "nuevos": nuevos, "estables": estables, "cambiados": cambiados, "fallidos": fallidos,
               "total_universo": len(store), "cola_restante": len(nueva_cola)}
    (base / "contactos_reporte.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  contactos: nuevos=%d estables=%d cambiados=%d fallidos=%d | universo=%d cola=%d" %
          (nuevos, estables, cambiados, fallidos, len(store), len(nueva_cola)))
    return resumen



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
    p1.add_argument("--portal", default="metrocuadrado")
    p1.add_argument("--tipos", default="")
    p1.add_argument("--cursor-suffix", default="", dest="cursor_suffix")
    p1.add_argument("--barrios", type=int, default=0)
    p2 = sub.add_parser("diagnostico")
    p2.add_argument("--carpeta", default="data")
    pc = sub.add_parser("contactos")
    pc.add_argument("--carpeta", default="data")
    pc.add_argument("--max", type=int, default=CONTACTO_MAX_POR_CORRIDA)
    args = parser.parse_args()
    if args.cmd == "doctor":
        doctor()
    elif args.cmd == "publicar":
        _tipos = [t.strip() for t in args.tipos.split(",") if t.strip()] or None
        publicar(args.carpeta, args.grupo, args.portal, _tipos, args.cursor_suffix, (args.barrios or None))
    elif args.cmd == "diagnostico":
        diagnostico(args.carpeta)
    elif args.cmd == "contactos":
        enriquecer_contactos(args.carpeta, args.max)
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

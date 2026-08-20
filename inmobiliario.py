#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  MONITOR INMOBILIARIO  —  Opción B (sin costos recurrentes, auto-mantenible)
================================================================================
Hace tres cosas:
  1. BUSCAR    inmuebles según criterios (para el cliente arrendatario/comprador)
  2. AVALUO    resumen de precios de mercado en una zona (para el propietario)
  3. NOTICIAS  titulares recientes del sector inmobiliario
  Y un modo:
  4. DOCTOR    revisa qué fuentes funcionan y cuál se rompió (mantenimiento)

Está pensado para tocarse lo MENOS posible. Si un portal cambia y deja de
funcionar, NO tienes que programar: el modo DOCTOR te genera un archivo y un
mensaje listo para pegar en Claude, que te devuelve la línea a corregir.

>>> Instrucciones de instalación y uso: ver la "GUIA_MANTENIMIENTO.md" <<<
================================================================================
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Dependencias externas (se instalan una sola vez, ver la guía) ---
try:
    import pandas as pd
    import requests
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Faltan librerías. Abre la GUIA_MANTENIMIENTO.md, sección 'Instalación'.")
    sys.exit(1)


# ##############################################################################
# #                                                                            #
# #     ZONA EDITABLE  —  AQUÍ SÍ PUEDES CAMBIAR COSAS SIN MIEDO               #
# #     (cambia ciudades, zonas, filtros. NO toques nada debajo del aviso.)   #
# #                                                                            #
# ##############################################################################

CIUDAD_POR_DEFECTO = "bogota"

# Portales de inmuebles usados / arriendo / venta.
# 'url' usa {operacion} {tipo} {zona} {ciudad} {pagina}. Si un portal cambia su
# forma de URL o deja de funcionar, el modo DOCTOR te dirá cuál y cómo arreglarlo.
PORTALES = {
    "metrocuadrado": {
        "url": "https://www.metrocuadrado.com/{tipo}/{operacion}/{ciudad}/{zona}/?page={pagina}",
        "css_tarjeta": "div[data-id]",              # <-- selector de contingencia
        "css_precio": "[class*='price'],[class*='precio']",
        "css_titulo": "h2,[class*='title']",
        "css_area": "[class*='area']",
        "css_hab": "[class*='bed'],[class*='habitac']",
        "css_ubic": "[class*='location'],[class*='ubicac']",
    },
    "fincaraiz": {
        "url": "https://www.fincaraiz.com.co/{operacion}/{tipo}/{zona}/{ciudad}?pagina={pagina}",
        "css_tarjeta": "div[class*='listingCard'],article",
        "css_precio": "[class*='price']",
        "css_titulo": "[class*='title'],h2",
        "css_area": "[class*='area']",
        "css_hab": "[class*='bedroom'],[class*='room']",
        "css_ubic": "[class*='location']",
    },
    # Puedes añadir ciencuadras / properati copiando un bloque igual.
}

# Agregadores de OBRA NUEVA (una sola dirección reúne muchas constructoras).
AGREGADORES_OBRA_NUEVA = {
    "estrenarvivienda": "https://www.estrenarvivienda.com/{ciudad}",
}

# Fuentes de NOTICIAS del sector (páginas índice; se leen los titulares).
NOTICIAS = {
    "La República":  "https://www.larepublica.co/camacol",
    "Portafolio":    "https://www.portafolio.co/noticias-economicas/sector-inmobiliario",
    "Valora Analitik": "https://www.valoraanalitik.com/",
    "El Colombiano": "https://www.elcolombiano.com/cronologia/noticias/meta/sector-inmobiliario",
    "Oikos":         "https://www.oikos.com.co/inmobiliaria/noticias-inmobiliaria",
    "Camacol":       "https://camacol.co/actualidad/noticias",
}

# Ritmo (segundos entre páginas). Súbelo si un portal te bloquea; no lo bajes.
PAUSA = 2.5
PAGINAS_POR_DEFECTO = 5

# ############################################################################
# #  CONSULTAS QUE SE PUBLICAN SOLAS (las corre GitHub Actions y las carga    #
# #  Alamo-IS). Añade/quita filas aquí. 'clave' es el nombre corto del        #
# #  archivo; 'etiqueta' es lo que verás en la app.                           #
# ############################################################################
PUBLICAR = [
    {"clave": "venta_apto_chapinero",   "etiqueta": "Venta · Apto · Chapinero",
     "portal": "metrocuadrado", "operacion": "venta",    "tipo": "apartamento", "zona": "chapinero"},
    {"clave": "arriendo_apto_chapinero","etiqueta": "Arriendo · Apto · Chapinero",
     "portal": "metrocuadrado", "operacion": "arriendo", "tipo": "apartamento", "zona": "chapinero"},
]
PUBLICAR_NOTICIAS = True   # incluir noticias del sector en la publicación

# ##############################################################################
# #                                                                            #
# #     AVISO: NO EDITES NADA DEBAJO DE ESTA LÍNEA                             #
# #     Si algo se rompe, usa el modo DOCTOR. No hace falta tocar el código.   #
# #                                                                            #
# ##############################################################################


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _num(texto):
    if not texto:
        return None
    d = re.sub(r"[^\d]", "", str(texto))
    return int(d) if d else None


def _carpeta(nombre):
    p = Path(nombre)
    p.mkdir(exist_ok=True)
    return p


def _abrir_pagina(browser, url):
    page = browser.new_context(
        locale="es-CO",
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"),
    ).new_page()
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    return page


# ---------------------------------------------------------------------------
# ESTRATEGIAS DE EXTRACCIÓN (de más estable a menos)
#   1) JSON-LD  (schema.org) -> nombres de campo fijos, casi nunca cambia
#   2) __NEXT_DATA__          -> estado JSON de la página
#   3) CSS                    -> contingencia (lo que más se rompe)
# ---------------------------------------------------------------------------
def _desde_jsonld(page):
    filas = []
    for b in page.query_selector_all('script[type="application/ld+json"]'):
        try:
            data = json.loads(b.inner_text())
        except Exception:
            continue
        for item in (data if isinstance(data, list) else [data]):
            tipo = item.get("@type", "")
            if any(k in str(tipo) for k in ("Product", "Residence", "Apartment",
                                            "House", "Offer", "RealEstate")):
                offer = item.get("offers", {}) or {}
                filas.append({
                    "titulo": item.get("name"),
                    "precio": _num(offer.get("price") or item.get("price")),
                    "area_m2": _num((item.get("floorSize") or {}).get("value")
                                    if isinstance(item.get("floorSize"), dict) else None),
                    "habitaciones": _num(item.get("numberOfRooms")),
                    "ubicacion": (item.get("address", {}) or {}).get("addressLocality")
                                 if isinstance(item.get("address"), dict) else None,
                    "url": item.get("url"),
                    "_fuente": "json-ld",
                })
    return filas


def _desde_next_data(page):
    el = page.query_selector("#__NEXT_DATA__")
    if not el:
        return []
    try:
        data = json.loads(el.inner_text())
    except Exception:
        return []
    filas = []

    def buscar(obj):
        if isinstance(obj, dict):
            tiene_precio = any(k in obj for k in ("price", "precio", "salePrice"))
            tiene_area = any(k in obj for k in ("area", "areaConstruida", "builtArea", "m2"))
            if tiene_precio and tiene_area:
                filas.append({
                    "titulo": obj.get("title") or obj.get("titulo") or obj.get("name"),
                    "precio": _num(obj.get("price") or obj.get("precio") or obj.get("salePrice")),
                    "area_m2": _num(obj.get("area") or obj.get("areaConstruida")
                                    or obj.get("builtArea") or obj.get("m2")),
                    "habitaciones": _num(obj.get("rooms") or obj.get("bedrooms")
                                         or obj.get("habitaciones")),
                    "ubicacion": obj.get("neighborhood") or obj.get("barrio")
                                 or obj.get("location") or obj.get("city"),
                    "url": obj.get("url") or obj.get("link"),
                    "_fuente": "next-data",
                })
            for v in obj.values():
                buscar(v)
        elif isinstance(obj, list):
            for v in obj:
                buscar(v)

    buscar(data)
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
            "area_m2": _num(tx(cfg["css_area"])),
            "habitaciones": _num(tx(cfg["css_hab"])),
            "ubicacion": tx(cfg["css_ubic"]),
            "url": href,
            "_fuente": "css",
        })
    return filas


def extraer(page, cfg):
    """Prueba las estrategias en orden y devuelve la primera que da buenos datos."""
    for estrategia in (_desde_jsonld, _desde_next_data):
        filas = estrategia(page)
        if _validar(filas)[0]:
            return filas
    return _desde_css(page, cfg)  # contingencia


# ---------------------------------------------------------------------------
# VALIDACIÓN (detecta ruptura silenciosa)
# ---------------------------------------------------------------------------
def _validar(filas, min_filas=3, max_vacios=0.4):
    problemas = []
    if len(filas) < min_filas:
        problemas.append(f"muy pocos resultados ({len(filas)})")
    if filas:
        vacios = sum(1 for f in filas if not f.get("precio")) / len(filas)
        if vacios > max_vacios:
            problemas.append(f"precios vacíos en {vacios:.0%} de los resultados")
    return (len(problemas) == 0), problemas


# ---------------------------------------------------------------------------
# SCRAPING de un portal
# ---------------------------------------------------------------------------
def scrape_portal(portal, operacion, tipo, zona, ciudad, paginas):
    cfg = PORTALES[portal]
    todos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for n in range(1, paginas + 1):
            url = cfg["url"].format(operacion=operacion, tipo=tipo, zona=zona,
                                    ciudad=ciudad, pagina=n)
            print(f"  [{portal} {n}/{paginas}] leyendo...")
            try:
                page = _abrir_pagina(browser, url)
                filas = extraer(page, cfg)
                if not filas:
                    break
                todos.extend(filas)
            except Exception as e:
                print(f"    aviso: {e}")
            time.sleep(PAUSA)
        browser.close()
    # dedup por url
    vistos, unicos = set(), []
    for f in todos:
        k = f.get("url") or json.dumps(f, ensure_ascii=False)
        if k not in vistos:
            vistos.add(k)
            unicos.append(f)
    return unicos


# ---------------------------------------------------------------------------
# NOTICIAS (lectura ligera de titulares)
# ---------------------------------------------------------------------------
def leer_noticias(maximo=8):
    resultados = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for medio, url in NOTICIAS.items():
            try:
                page = _abrir_pagina(browser, url)
                vistos = set()
                for a in page.query_selector_all("article a, h2 a, h3 a"):
                    txt = (a.inner_text() or "").strip()
                    href = a.get_attribute("href") or ""
                    if len(txt) > 30 and href and txt not in vistos:
                        vistos.add(txt)
                        if href.startswith("/"):
                            href = url.split("/", 3)[0] + "//" + url.split("/")[2] + href
                        resultados.append({"medio": medio, "titular": txt, "url": href})
                    if len([r for r in resultados if r["medio"] == medio]) >= maximo:
                        break
            except Exception as e:
                print(f"  aviso ({medio}): {e}")
        browser.close()
    return resultados


# ---------------------------------------------------------------------------
# RESUMEN DE MERCADO (avalúo)
# ---------------------------------------------------------------------------
def resumen_mercado(df):
    precios = df["precio"].dropna()
    if precios.empty:
        return {}
    da = df.dropna(subset=["precio", "area_m2"])
    da = da[da["area_m2"] > 0]
    pm2 = (da["precio"] / da["area_m2"]) if not da.empty else pd.Series(dtype=float)
    return {
        "muestra": len(precios),
        "precio_minimo": int(precios.min()),
        "precio_maximo": int(precios.max()),
        "precio_promedio": int(precios.mean()),
        "precio_mediana": int(precios.median()),
        "precio_m2_promedio": int(pm2.mean()) if not pm2.empty else "sin dato",
        "precio_m2_mediana": int(pm2.median()) if not pm2.empty else "sin dato",
    }


def exportar_excel(df, resumen, etiqueta):
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / f"{etiqueta}_{fecha}.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="Listados", index=False)
        if resumen:
            (pd.DataFrame([resumen]).T.rename(columns={0: "valor"})
             .to_excel(xl, sheet_name="Resumen_mercado"))
    return ruta


# ---------------------------------------------------------------------------
# EXPORT PARA "Alamo Team - IS"  (contrato interno · se importa en 5·E.Mercado)
# ---------------------------------------------------------------------------
def _df_a_contrato(df, portal, operacion, tipo):
    """df crudo -> lista de inmuebles en el esquema interno de Alamo-IS."""
    oper = {"venta": "Venta", "arriendo": "Arriendo"}.get(operacion, operacion)
    inmuebles = []
    for idx, r in df.reset_index(drop=True).iterrows():
        def g(k):
            v = r.get(k)
            return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
        inmuebles.append({
            "id": f"MI-{idx+1}",
            "operacion": [oper],
            "tipo": tipo,
            "precio": g("precio"),
            "area": g("area_m2"),
            "administracion": None,
            "barrio": (str(g("ubicacion")).upper() if g("ubicacion") else ""),
            "direccion": "",
            "habitaciones": g("habitaciones"),
            "portalNombre": portal,
            "sourceLink": g("url"),
            "titulo": g("titulo"),
            "location_type": "aproximada",
        })
    return inmuebles


def exportar_alamo_json(df, args, etiqueta):
    """Escribe *_alamo.json normalizado al esquema interno del artefacto HTML."""
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / f"{etiqueta}_{fecha}_alamo.json"
    inmuebles = _df_a_contrato(df, args.portal, args.operacion, args.tipo)
    payload = {"ok": True, "total": len(inmuebles), "inmuebles": inmuebles}
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def exportar_noticias_json(items):
    """Escribe noticias_*_alamo.json para importar en 7·Informes."""
    _carpeta("resultados")
    fecha = datetime.now().strftime("%Y%m%d_%H%M")
    ruta = Path("resultados") / f"noticias_{fecha}_alamo.json"
    noticias = [{
        "titulo": it.get("titular", ""),
        "fuente": it.get("medio", ""),
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "resumen": "",
        "url": it.get("url", ""),
    } for it in items]
    ruta.write_text(json.dumps({"noticias": noticias}, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# MODO DOCTOR (mantenimiento sin programar)
# ---------------------------------------------------------------------------
def doctor():
    print("\n=== DIAGNÓSTICO DE FUENTES ===\n")
    rotos = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for portal, cfg in PORTALES.items():
            url = cfg["url"].format(operacion="arriendo", tipo="apartamento",
                                    zona="chapinero", ciudad=CIUDAD_POR_DEFECTO, pagina=1)
            try:
                page = _abrir_pagina(browser, url)
                filas = extraer(page, cfg)
                ok, probs = _validar(filas)
                if ok:
                    fuente = filas[0].get("_fuente", "?") if filas else "?"
                    print(f"  ✔ {portal:16} OK  ({len(filas)} resultados vía {fuente})")
                else:
                    print(f"  �’ {portal:16} FALLA: {', '.join(probs)}")
                    snap = _guardar_snapshot(page, portal)
                    rotos.append((portal, snap, probs))
            except Exception as e:
                print(f"  ✗ {portal:16} ERROR de conexión: {e}")
                rotos.append((portal, None, [str(e)]))
        browser.close()

    if not rotos:
        print("\nTodo funciona. No hay nada que hacer.\n")
        return

    print("\n--- HAY FUENTES QUE NECESITAN REPARACIÓN ---")
    print("No tienes que programar. Sigue la GUIA_MANTENIMIENTO.md, sección")
    print("'Cuando una fuente se rompe'. Copia y pega en Claude este mensaje:\n")
    for portal, snap, probs in rotos:
        print(f"  • Portal '{portal}': {', '.join(probs)}.")
        if snap:
            print(f"    Sube a Claude este archivo: {snap}")
    print("\nClaude te devolverá la línea exacta a reemplazar. Fin.\n")


def _guardar_snapshot(page, portal):
    carpeta = _carpeta("diagnostico")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = carpeta / f"{portal}_{ts}.html"
    ruta.write_text(page.content(), encoding="utf-8")
    return ruta


# ---------------------------------------------------------------------------
# LÍNEA DE COMANDOS
# ---------------------------------------------------------------------------
def publicar(carpeta="data"):
    """Corre las consultas de PUBLICAR y escribe data/ + index.json (manifiesto).
       Es el modo que ejecuta GitHub Actions; Alamo-IS lee esa carpeta."""
    base = Path(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    generado = datetime.now()
    datasets = []
    for cfg in PUBLICAR:
        print(f"\n== Publicando: {cfg['etiqueta']} ==")
        try:
            filas = scrape_portal(cfg["portal"], cfg["operacion"], cfg["tipo"],
                                  cfg["zona"], CIUDAD_POR_DEFECTO, PAGINAS_POR_DEFECTO)
            df = pd.DataFrame(filas)
            inmuebles = _df_a_contrato(df, cfg["portal"], cfg["operacion"], cfg["tipo"]) if not df.empty else []
        except Exception as e:
            print(f"  aviso: {e}")
            inmuebles = []
        archivo = f"{cfg['clave']}.json"
        (base / archivo).write_text(
            json.dumps({"ok": True, "total": len(inmuebles), "inmuebles": inmuebles},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        datasets.append({"clave": cfg["clave"], "etiqueta": cfg["etiqueta"],
                         "archivo": archivo, "total": len(inmuebles),
                         "operacion": cfg["operacion"], "tipo": cfg["tipo"], "zona": cfg["zona"]})
        print(f"  {len(inmuebles)} inmueble(s) -> {archivo}")

    noticias_meta = None
    if PUBLICAR_NOTICIAS:
        try:
            items = leer_noticias()
        except Exception as e:
            print(f"  aviso noticias: {e}"); items = []
        noticias = [{"titulo": it.get("titular", ""), "fuente": it.get("medio", ""),
                     "fecha": generado.strftime("%Y-%m-%d"), "resumen": "",
                     "url": it.get("url", "")} for it in items]
        (base / "noticias.json").write_text(
            json.dumps({"noticias": noticias}, ensure_ascii=False, indent=2), encoding="utf-8")
        noticias_meta = {"archivo": "noticias.json", "total": len(noticias)}
        print(f"\n  {len(noticias)} noticia(s) -> noticias.json")

    manifiesto = {
        "generado": generado.isoformat(timespec="seconds"),
        "generado_humano": generado.strftime("%Y.") +
            ["ENE","FEB","MAR","ABR","MAY","JUN","JUL","AGO","SEP","OCT","NOV","DIC"][generado.month-1] +
            generado.strftime(".%d %H:%M"),
        "ciudad": CIUDAD_POR_DEFECTO,
        "datasets": datasets,
        "noticias": noticias_meta,
    }
    (base / "index.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifiesto escrito: {(base/'index.json').resolve()}")
    print(f"Última corrida: {manifiesto['generado_humano']}")
    return manifiesto


def main():
    ap = argparse.ArgumentParser(description="Monitor inmobiliario (opción B).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("buscar", help="Buscar inmuebles según criterios del cliente")
    b.add_argument("--portal", required=True, choices=PORTALES.keys())
    b.add_argument("--operacion", required=True, choices=["arriendo", "venta"])
    b.add_argument("--tipo", required=True)
    b.add_argument("--zona", required=True)
    b.add_argument("--ciudad", default=CIUDAD_POR_DEFECTO)
    b.add_argument("--paginas", type=int, default=PAGINAS_POR_DEFECTO)
    b.add_argument("--precio_min", type=int)
    b.add_argument("--precio_max", type=int)
    b.add_argument("--habitaciones_min", type=int)
    b.add_argument("--area_min", type=int)

    a = sub.add_parser("avaluo", help="Resumen de precios de mercado en una zona")
    a.add_argument("--portal", required=True, choices=PORTALES.keys())
    a.add_argument("--operacion", required=True, choices=["arriendo", "venta"])
    a.add_argument("--tipo", required=True)
    a.add_argument("--zona", required=True)
    a.add_argument("--ciudad", default=CIUDAD_POR_DEFECTO)
    a.add_argument("--paginas", type=int, default=PAGINAS_POR_DEFECTO)

    sub.add_parser("noticias", help="Titulares recientes del sector")
    sub.add_parser("doctor", help="Revisar qué fuentes funcionan (mantenimiento)")
    pp = sub.add_parser("publicar", help="Corre las consultas de PUBLICAR y escribe data/ (para Alamo-IS)")
    pp.add_argument("--carpeta", default="data")

    args = ap.parse_args()

    if args.cmd == "doctor":
        doctor()

    elif args.cmd == "publicar":
        publicar(args.carpeta)

    elif args.cmd == "noticias":
        items = leer_noticias()
        if not items:
            print("Sin titulares. Corre 'doctor' para ver si las fuentes cambiaron.")
            return
        for it in items:
            print(f"\n[{it['medio']}] {it['titular']}\n   {it['url']}")
        ruta_j = exportar_noticias_json(items)
        print(f"\nArchivo para Alamo Team (7·Informes): {ruta_j.resolve()}")

    elif args.cmd in ("buscar", "avaluo"):
        filas = scrape_portal(args.portal, args.operacion, args.tipo,
                              args.zona, args.ciudad, args.paginas)
        df = pd.DataFrame(filas)
        if df.empty:
            print("Sin datos. Corre 'doctor' para diagnosticar.")
            return

        if args.cmd == "buscar":
            if args.precio_min: df = df[df["precio"] >= args.precio_min]
            if args.precio_max: df = df[df["precio"] <= args.precio_max]
            if args.habitaciones_min: df = df[df["habitaciones"] >= args.habitaciones_min]
            if args.area_min: df = df[df["area_m2"] >= args.area_min]

        resumen = resumen_mercado(df)
        print("\n=== RESUMEN DE MERCADO ===")
        for k, v in resumen.items():
            print(f"  {k:20}: {v:,}" if isinstance(v, int) else f"  {k:20}: {v}")

        etiqueta = f"{args.cmd}_{args.portal}_{args.operacion}_{args.tipo}_{args.zona}"
        ruta = exportar_excel(df, resumen, etiqueta)
        print(f"\nGuardado en: {ruta.resolve()}")
        ruta_j = exportar_alamo_json(df, args, etiqueta)
        print(f"Archivo para Alamo Team (5·E.Mercado): {ruta_j.resolve()}")


if __name__ == "__main__":
    main()

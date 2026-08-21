#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MONITOR INMOBILIARIO — Opción B (sin costos recurrentes, auto-mantenible)
Comandos: buscar | avaluo | noticias | doctor | publicar | diagnostico
Ver GUIA_MANTENIMIENTO.md
"""

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
    print("Faltan librerías. Abre la GUIA_MANTENIMIENTO.md, sección 'Instalación'.")
    sys.exit(1)


# ############################################################################
# #   ZONA EDITABLE — cambia ciudades/zonas/consultas sin miedo.             #
# #   NO toques nada debajo del aviso de más abajo.                          #
# ############################################################################

CIUDAD_POR_DEFECTO = "bogota"

PORTALES = {
    "metrocuadrado": {
        "url": "https://www.metrocuadrado.com/{tipo}/{operacion}/{ciudad}/{zona}/?page={pagina}",
        "css_tarjeta": "div[data-id]",
        "css_precio": "[class*='price'],[class*='precio']",
        "css_titulo": "h2,[class*='title']",
        "css_area": "[class*='area']",
        "css_hab": "[class*='bed'],[class*='habitac']",
        "css_ubic": "[class*='location'],[class*='ubicac']",
    },
    "fincaraiz": {
        "url": "https://www.fincaraiz.com.co/{operacion}/{tipo}/{ciudad}/{zona}?pagina={pagina}",
        "css_tarjeta": "div[class*='listingCard'],article",
        "css_precio": "[class*='price']",
        "css_titulo": "[class*='title'],h2",
        "css_area": "[class*='area']",
        "css_hab": "[class*='bedroom'],[class*='room']",
        "css_ubic": "[class*='location']",
    },
}

AGREGADORES_OBRA_NUEVA = {
    "estrenarvivienda": "https://www.estrenarvivienda.com/{ciudad}",
}

NOTICIAS = {
    "La República":  "https://www.larepublica.co/camacol",
    "Portafolio":    "https://www.portafolio.co/noticias-economicas/sector-inmobiliario",
    "Valora Analitik": "https://www.valoraanalitik.com/",
    "El Colombiano": "https://www.elcolombiano.com/cronologia/noticias/meta/sector-inmobiliario",
    "Oikos":         "https://www.oikos.com.co/inmobiliaria/noticias-inmobiliaria",
    "Camacol":       "https://camacol.co/actualidad/noticias",
}

PAUSA = 2.5
PAGINAS_POR_DEFECTO = 5

PUBLICAR = [
    {"clave": "venta_apto_chapinero",   "etiqueta": "Venta · Apto · Chapinero",
     "portal": "metrocuadrado", "operacion": "venta",    "tipo": "apartamento", "zona": "chapinero"},
    {"clave": "arriendo_apto_chapinero","etiqueta": "Arriendo · Apto · Chapinero",
     "portal": "metrocuadrado", "operacion": "arriendo", "tipo": "apartamento", "zona": "chapinero"},
]
PUBLICAR_NOTICIAS = True

# ############################################################################
# #   AVISO: NO EDITES NADA DEBAJO DE ESTA LÍNEA.                            #
# ############################################################################


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
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")).new_page()
    page.goto(url, timeout=45000, wait_until="domcontentloaded")
    page.wait_for_timeout(3500)
    return page


def _desde_jsonld(page):
    filas = []
    for el in page.query_selector_all('script[type="application/ld+json"]'):
        try:
            data = json.loads(el.inner_text())
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if not isinstance(it, dict):
                continue
            if it.get("@type") in ("Product", "Offer", "Residence", "Apartment", "House"):
                offer = it.get("offers") or {}
                filas.append({
                    "titulo": it.get("name"),
                    "precio": _num(offer.get("price") or it.get("price")),
                    "area_m2": _dec(it.get("floorSize", {}).get("value") if isinstance(it.get("floorSize"), dict) else None),
                    "habitaciones": _num(it.get("numberOfRooms")),
                    "ubicacion": (it.get("address") or {}).get("addressLocality") if isinstance(it.get("address"), dict) else None,
                    "url": it.get("url"),
                    "_fuente": "json-ld",
                })
    return filas


def _desde_metrocuadrado(page):
    """Metrocuadrado embebe los resultados oficiales en self.__next_f.push([1,"...initialResults...results:[...]"])."""
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
    txt = raw.encode('utf-8').decode('unicode_escape')
    try:
        results = json.loads(txt)
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
    """Fincaraíz (Next.js): inmuebles en __NEXT_DATA__ -> props.pageProps.fetchResult.searchFast.data[]."""
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
        barrio = ((loc.get("location_main") or {}).get("name")
                  or (loc.get("neighbourhood") or [{}])[0].get("name"))
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
                    "area_m2": _dec(obj.get("area") or obj.get("areaConstruida")
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
            "area_m2": _dec(tx(cfg["css_area"])),
            "habitaciones": _num(tx(cfg["css_hab"])),
            "ubicacion": tx(cfg["css_ubic"]),
            "url": href,
            "_fuente": "css",
        })
    return filas


def extraer(page, cfg):
    """Prueba las estrategias en orden y devuelve la primera que da buenos datos."""
    for estrategia in (_desde_metrocuadrado, _desde_fincaraiz, _desde_jsonld, _desde_next_data):
        filas = estrategia(page)
        if _validar(filas)[0]:
            return filas
    return _desde_css(page, cfg)


def _validar(filas, min_filas=3, max_vacios=0.4):
    problemas = []
    if len(filas) < min_filas:
        problemas.append(f"muy pocos resultados ({len(filas)})")
    if filas:
        vacios = sum(1 for f in filas if not f.get("precio")) / len(filas)
        if vacios > max_vacios:
            problemas.append(f"precios vacíos en {vacios:.0%} de los resultados")
    return (len(problemas) == 0), problemas
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
        areas = df["area_m2"].dropna()
        if not areas.empty and precios.sum() > 0:
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
            print(f"  aviso ({medio}): {e}")
    return items


def _carpeta_resultados():
    return _carpeta("resultados")


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
    ruta = Path("resultados") / f"{etiqueta}_{fecha}_alamo.json"
    inmuebles = _df_a_contrato(df, args.portal, args.operacion, args.tipo)
    payload = {"ok": True, "total": len(inmuebles), "inmuebles": inmuebles}
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def exportar_noticias_json(items):
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
  def diagnostico(carpeta="data"):
    """Guarda el HTML real de cada portal + resumen, para calibrar (corre en la nube)."""
    base = Path(carpeta) / "diagnostico"
    base.mkdir(parents=True, exist_ok=True)
    casos = []
    for portal, cfg in PORTALES.items():
        for oper in ("venta", "arriendo"):
            url = cfg["url"].format(tipo="apartamento", operacion=oper,
                                    ciudad=CIUDAD_POR_DEFECTO, zona="chapinero", pagina=1)
            casos.append((f"{portal}_{oper}", portal, url))
    resumen = {"generado": datetime.now().isoformat(timespec="seconds"), "casos": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for nombre, portal, url in casos:
            info = {"nombre": nombre, "portal": portal, "url": url}
            try:
                page = _abrir_pagina(browser, url)
                info["url_final"] = page.url
                info["titulo"] = page.title()
                info["jsonld_bloques"] = len(page.query_selector_all('script[type="application/ld+json"]'))
                info["next_data"] = bool(page.query_selector("#__NEXT_DATA__"))
                html = page.content()
                info["html_bytes"] = len(html)
                (base / f"{nombre}.html").write_text(html, encoding="utf-8")
                nd = page.query_selector("#__NEXT_DATA__")
                if nd:
                    (base / f"{nombre}__NEXT_DATA__.json").write_text(nd.inner_text(), encoding="utf-8")
            except Exception as e:
                info["error"] = str(e)
            resumen["casos"].append(info)
            print(f"  {nombre}: next={info.get('next_data')} jsonld={info.get('jsonld_bloques')} -> {nombre}.html")
        browser.close()
    (base / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDiagnóstico escrito en {base.resolve()}")
    return resumen


def publicar(carpeta="data"):
    """Corre las consultas de PUBLICAR y escribe data/ + index.json (para Alamo-IS)."""
    base = Path(carpeta)
    base.mkdir(parents=True, exist_ok=True)
    generado = datetime.now()
    MES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
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
            print(f"  aviso noticias: {e}")
            items = []
        noticias = [{"titulo": it.get("titular", ""), "fuente": it.get("medio", ""),
                     "fecha": generado.strftime("%Y-%m-%d"), "resumen": "",
                     "url": it.get("url", "")} for it in items]
        (base / "noticias.json").write_text(
            json.dumps({"noticias": noticias}, ensure_ascii=False, indent=2), encoding="utf-8")
        noticias_meta = {"archivo": "noticias.json", "total": len(noticias)}
        print(f"\n  {len(noticias)} noticia(s) -> noticias.json")

    manifiesto = {
        "generado": generado.isoformat(timespec="seconds"),
        "generado_humano": generado.strftime("%Y.") + MES[generado.month - 1] + generado.strftime(".%d %H:%M"),
        "ciudad": CIUDAD_POR_DEFECTO,
        "datasets": datasets,
        "noticias": noticias_meta,
    }
    (base / "index.json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifiesto: {(base/'index.json').resolve()}")
    print(f"Última corrida: {manifiesto['generado_humano']}")
    return manifiesto


def doctor():
    print("Revisando portales...\n")
    for portal, cfg in PORTALES.items():
        url = cfg["url"].format(operacion="venta", tipo="apartamento",
                                ciudad=CIUDAD_POR_DEFECTO, zona="chapinero", pagina=1)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = _abrir_pagina(browser, url)
                filas = extraer(page, cfg)
                ok, problemas = _validar(filas)
                browser.close()
            estado = "OK" if ok else "REVISAR"
            print(f"[{estado}] {portal}: {len(filas)} resultado(s). {'; '.join(problemas)}")
        except Exception as e:
            print(f"[ERROR] {portal}: {e}")
    print("\nSi algo dice REVISAR o ERROR, sube el mensaje a Claude para calibrar.")
  def main():
    parser = argparse.ArgumentParser(description="Monitor Inmobiliario")
    sub = parser.add_subparsers(dest="cmd")

    pb = sub.add_parser("buscar", help="Buscar inmuebles según criterios")
    pb.add_argument("--portal", default="metrocuadrado")
    pb.add_argument("--operacion", default="venta")
    pb.add_argument("--tipo", default="apartamento")
    pb.add_argument("--zona", default="chapinero")
    pb.add_argument("--ciudad", default=CIUDAD_POR_DEFECTO)
    pb.add_argument("--paginas", type=int, default=PAGINAS_POR_DEFECTO)

    pa = sub.add_parser("avaluo", help="Resumen de precios de una zona")
    pa.add_argument("--portal", default="metrocuadrado")
    pa.add_argument("--operacion", default="venta")
    pa.add_argument("--tipo", default="apartamento")
    pa.add_argument("--zona", default="chapinero")
    pa.add_argument("--ciudad", default=CIUDAD_POR_DEFECTO)
    pa.add_argument("--paginas", type=int, default=PAGINAS_POR_DEFECTO)

    sub.add_parser("noticias", help="Titulares recientes del sector")
    sub.add_parser("doctor", help="Revisar qué fuentes funcionan (mantenimiento)")
    pp = sub.add_parser("publicar", help="Corre PUBLICAR y escribe data/ (para Alamo-IS)")
    pp.add_argument("--carpeta", default="data")
    dg = sub.add_parser("diagnostico", help="Guarda el HTML real de cada portal para calibrar")
    dg.add_argument("--carpeta", default="data")

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
            print(f"\n[{it['medio']}] {it['titular']}\n   {it['url']}")
        ruta_j = exportar_noticias_json(items)
        print(f"\nArchivo para Alamo Team (7·Informes): {ruta_j.resolve()}")

    elif args.cmd in ("buscar", "avaluo"):
        etiqueta = f"{args.cmd}_{args.operacion}_{args.tipo}_{args.zona}"
        filas = scrape_portal(args.portal, args.operacion, args.tipo,
                              args.zona, args.ciudad, args.paginas)
        df = pd.DataFrame(filas)
        if df.empty:
            print("No se encontraron resultados. Corre 'doctor' para revisar.")
            return
        resumen = resumen_mercado(df)
        print("\nResumen de mercado:")
        for k, v in resumen.items():
            print(f"  {k}: {v}")
        ruta = exportar_excel(df, resumen, etiqueta)
        print(f"\nGuardado en: {ruta.resolve()}")
        ruta_j = exportar_alamo_json(df, args, etiqueta)
        print(f"Archivo para Alamo Team (5·E.Mercado): {ruta_j.resolve()}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
  

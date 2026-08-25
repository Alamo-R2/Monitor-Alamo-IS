# -*- coding: utf-8 -*-
"""
Cruce de nombres (Metrocuadrado / dataset) contra geo_model.json,
independiente de mayúsculas, tildes, espacios y puntuación.
Misma regla que 'normKey' en la app (Alamo).
"""
import json, unicodedata, re

def norm_key(s):
    s = '' if s is None else str(s)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # quita tildes
    s = s.upper()
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)   # puntuación -> espacio
    s = re.sub(r'\s+', ' ', s).strip()  # colapsa espacios
    return s

def construir_indice(geo_model):
    """Devuelve { clave_normalizada : {'upl':..., 'barrio_canonico':...} }.
       Incluye barrios y sus alias."""
    idx = {}
    for upl, v in geo_model['upl'].items():
        idx.setdefault(norm_key(upl), {'upl': upl, 'barrio_canonico': None})  # UPL como tal
        for barrio, datos in v['barrios'].items():
            entrada = {'upl': upl, 'barrio_canonico': barrio}
            idx[norm_key(barrio)] = entrada
            for al in (datos.get('alias') or []):     # alias -> mismo canónico
                idx.setdefault(norm_key(al), entrada)
    return idx

def resolver(nombre, idx):
    """Match exacto normalizado -> 'contiene' controlado -> None (sin clasificar)."""
    k = norm_key(nombre)
    if k in idx:
        return idx[k]
    # fallback controlado: coincidencia por contención en ambos sentidos
    cand = [e for kk, e in idx.items() if kk and (kk in k or k in kk)]
    if len(cand) == 1:
        return cand[0]
    return None   # ambiguo o sin match: dejar 'sin clasificar', no forzar

# ---- Uso en el monitor ----
if __name__ == '__main__':
    geo = json.load(open('geo_model.json', encoding='utf-8'))
    idx = construir_indice(geo)

    for nombre in ['Bosque Medina', 'BOSQUE  MEDINA', 'bosque de pinos', 'Chicó Norte', 'Inventado 123']:
        r = resolver(nombre, idx)
        if r:
            print(f'{nombre!r:22} -> UPL {r["upl"]} / barrio {r["barrio_canonico"]}')
        else:
            print(f'{nombre!r:22} -> SIN CLASIFICAR')

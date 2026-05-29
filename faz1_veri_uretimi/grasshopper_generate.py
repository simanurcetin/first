# -*- coding: utf-8 -*-
# =============================================================================
# FAZ 1 - SENTETİK BİNA MODELİ ÜRETİCİSİ (Brep tabanlı)
# =============================================================================
#
# Grasshopper'da Trigger bileşeniyle tetiklenerek çalışır.
# Her tetiklemede 1 rastgele bina üretir, OBJ + JSON kaydeder.
#
# OBJ grup adları → sınıf etiketleri (01_obj_to_pointcloud.py okur):
#   zemin_*  → 1 (floor)     tavan_*  → 2 (ceiling)
#   *duvar   → 0 (wall)      *kapi_*  → 3 (door bölgesi)
#   *pen_*   → 4 (window bölgesi)
#   cati_*   → 5 (roof)      sacak_*  → 6 (eave)
#
# Grasshopper bağlantısı:
#   - Trigger bileşeni → bu scripte bağla (her tık = 1 model)
#   - 'a' çıktısı → Rhino viewport'ta renkli önizleme
# =============================================================================

import Rhino.Geometry as rg
import random
import json
import os
import time
import Rhino as _Rhino

# =============================================================================
# PROJE KLASÖRÜ
# =============================================================================

_sabit_yol = ""  # Otomatik bulunamazsa: r"C:\Users\ADINIZ\Desktop\lorddoga"

def _proje_klasoru_bul():
    try:
        _doc_yol = _Rhino.RhinoDoc.ActiveDoc.Path
        if _doc_yol:
            return os.path.dirname(_doc_yol)
    except:
        pass
    if _sabit_yol:
        return _sabit_yol
    _up = os.environ.get("USERPROFILE", "C:\\Users\\User")
    for _y in [
        os.path.join(_up, "OneDrive", "Masaustu",  "lorddoga"),
        os.path.join(_up, "OneDrive", "Masaüstü",  "lorddoga"),
        os.path.join(_up, "OneDrive", "Desktop",   "lorddoga"),
        os.path.join(_up, "Desktop",               "lorddoga"),
        os.path.join(_up, "Masaüstü",              "lorddoga"),
    ]:
        if os.path.isdir(_y):
            return _y
    return os.path.join(_up, "OneDrive", "Masaustu", "lorddoga")

_PROJE      = _proje_klasoru_bul()
OBJ_KLASORU  = os.path.join(_PROJE, "data", "obj_files")
JSON_KLASORU = os.path.join(_PROJE, "data", "json_files")

for _k in [OBJ_KLASORU, JSON_KLASORU]:
    if not os.path.exists(_k):
        os.makedirs(_k)

# =============================================================================
# BİNA ÜRETİCİ
# =============================================================================

x = round(random.uniform(4.0, 10.0), 2)
y = round(random.uniform(4.0, 10.0), 2)
z = round(random.uniform(2.4,  3.5), 2)
t = 0.2
katlar = random.choice([1, 2])

u       = round(random.uniform(0.8, min(1.2, x / 3)), 2)
v_kapi  = round(random.uniform(2.0, min(2.4, z - 0.2)), 2)
kapi_cephe  = random.choice(["on", "arka", "sol", "sag"])
kapi_offset = round(random.uniform(0.3, max(0.31, x - u - 0.3)), 2)

pen_cepheler = random.sample(["on", "arka", "sol", "sag"], random.randint(1, 4))
pen_g   = round(random.uniform(0.6, min(1.5, x / 3)), 2)
pen_y   = round(random.uniform(0.6, 1.0), 2)
pen_deniz = round(random.uniform(0.7, 1.0), 2)

cati_yukseklik = round(random.uniform(1.0, 2.0), 2)
sacak_g        = round(random.uniform(0.2, 0.6), 2)
sacak_cepheler = random.sample(["on", "arka", "sol", "sag"], random.randint(1, 4))

# ── Yardımcı ──────────────────────────────────────────────────

def kutu(x0, y0, z0, x1, y1, z1):
    bb = rg.BoundingBox(rg.Point3d(x0, y0, z0), rg.Point3d(x1, y1, z1))
    return rg.Box(bb).ToBrep()

def on_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_offset
        p["kapi_sol"] = kutu(0,    0, zb, ko,    t, zb + zh)
        p["kapi_sag"] = kutu(ko+u, 0, zb, x,     t, zb + zh)
        p["kapi_ust"] = kutu(ko,   0, zb + v_kapi, ko + u, t, zb + zh)
    elif pen:
        po = round(random.uniform(0.3, max(0.31, x - pen_g - 0.3)), 2)
        p["pen_sol"] = kutu(0,       0, zb,              po,       t, zb + zh)
        p["pen_sag"] = kutu(po+pen_g, 0, zb,             x,        t, zb + zh)
        p["pen_alt"] = kutu(po,       0, zb,              po+pen_g, t, zb + pen_deniz)
        p["pen_ust"] = kutu(po,       0, zb+pen_deniz+pen_y, po+pen_g, t, zb + zh)
    else:
        p["duvar"] = kutu(0, 0, zb, x, t, zb + zh)
    return p

def arka_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_offset
        p["kapi_sol"] = kutu(0,    y-t, zb, ko,    y, zb + zh)
        p["kapi_sag"] = kutu(ko+u, y-t, zb, x,     y, zb + zh)
        p["kapi_ust"] = kutu(ko,   y-t, zb + v_kapi, ko + u, y, zb + zh)
    elif pen:
        po = round(random.uniform(0.3, max(0.31, x - pen_g - 0.3)), 2)
        p["pen_sol"] = kutu(0,        y-t, zb,              po,       y, zb + zh)
        p["pen_sag"] = kutu(po+pen_g, y-t, zb,              x,        y, zb + zh)
        p["pen_alt"] = kutu(po,       y-t, zb,              po+pen_g, y, zb + pen_deniz)
        p["pen_ust"] = kutu(po,       y-t, zb+pen_deniz+pen_y, po+pen_g, y, zb + zh)
    else:
        p["duvar"] = kutu(0, y-t, zb, x, y, zb + zh)
    return p

def sol_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_offset
        p["kapi_sol"] = kutu(0, 0,    zb, t, ko,    zb + zh)
        p["kapi_sag"] = kutu(0, ko+u, zb, t, y,     zb + zh)
        p["kapi_ust"] = kutu(0, ko,   zb + v_kapi, t, ko + u, zb + zh)
    elif pen:
        po = round(random.uniform(0.3, max(0.31, y - pen_g - 0.3)), 2)
        p["pen_sol"] = kutu(0, 0,        zb,              t, po,       zb + zh)
        p["pen_sag"] = kutu(0, po+pen_g, zb,              t, y,        zb + zh)
        p["pen_alt"] = kutu(0, po,       zb,              t, po+pen_g, zb + pen_deniz)
        p["pen_ust"] = kutu(0, po,       zb+pen_deniz+pen_y, t, po+pen_g, zb + zh)
    else:
        p["duvar"] = kutu(0, 0, zb, t, y, zb + zh)
    return p

def sag_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_offset
        p["kapi_sol"] = kutu(x-t, 0,    zb, x, ko,    zb + zh)
        p["kapi_sag"] = kutu(x-t, ko+u, zb, x, y,     zb + zh)
        p["kapi_ust"] = kutu(x-t, ko,   zb + v_kapi, x, ko + u, zb + zh)
    elif pen:
        po = round(random.uniform(0.3, max(0.31, y - pen_g - 0.3)), 2)
        p["pen_sol"] = kutu(x-t, 0,        zb,              x, po,       zb + zh)
        p["pen_sag"] = kutu(x-t, po+pen_g, zb,              x, y,        zb + zh)
        p["pen_alt"] = kutu(x-t, po,       zb,              x, po+pen_g, zb + pen_deniz)
        p["pen_ust"] = kutu(x-t, po,       zb+pen_deniz+pen_y, x, po+pen_g, zb + zh)
    else:
        p["duvar"] = kutu(x-t, 0, zb, x, y, zb + zh)
    return p

def kat_uret(kat_no):
    zb = kat_no * z
    el = {}
    el["zemin_{}".format(kat_no)] = kutu(0, 0, zb,       x, y, zb + t)
    el["tavan_{}".format(kat_no)] = kutu(0, 0, zb+z-t,   x, y, zb + z)
    for cephe in ["on", "arka", "sol", "sag"]:
        has_kapi = (cephe == kapi_cephe and kat_no == 0)
        has_pen  = (cephe in pen_cepheler)
        prefix   = "{}_{}".format(cephe, kat_no)
        if   cephe == "on":   p = on_duvar  (zb, z, has_kapi, has_pen and not has_kapi)
        elif cephe == "arka": p = arka_duvar(zb, z, has_kapi, has_pen and not has_kapi)
        elif cephe == "sol":  p = sol_duvar (zb, z, has_kapi, has_pen and not has_kapi)
        else:                 p = sag_duvar (zb, z, has_kapi, has_pen and not has_kapi)
        for k, brep in p.items():
            el["{}_{}".format(prefix, k)] = brep
    return el

# ── Model ─────────────────────────────────────────────────────

tum = {}
for k in range(katlar):
    tum.update(kat_uret(k))

z_top = katlar * z
p0 = rg.Point3d(0,   0, z_top);  p1 = rg.Point3d(x,   0, z_top)
p2 = rg.Point3d(x,   y, z_top);  p3 = rg.Point3d(0,   y, z_top)
p4 = rg.Point3d(x/2, 0, z_top + cati_yukseklik)
p5 = rg.Point3d(x/2, y, z_top + cati_yukseklik)

for isim, pts in [
    ("cati_sol",  (p0, p4, p5, p3)),
    ("cati_sag",  (p4, p1, p2, p5)),
    ("cati_on",   (p0, p1, p4, p4)),
    ("cati_arka", (p3, p5, p2, p2)),
]:
    b = rg.Brep.CreateFromCornerPoints(pts[0], pts[1], pts[2], pts[3], 0.01)
    if b:
        tum[isim] = b

if "on"   in sacak_cepheler: tum["sacak_on"]   = kutu(-sacak_g, -sacak_g, z_top-t, x+sacak_g, 0,        z_top)
if "arka" in sacak_cepheler: tum["sacak_arka"]  = kutu(-sacak_g, y,        z_top-t, x+sacak_g, y+sacak_g, z_top)
if "sol"  in sacak_cepheler: tum["sacak_sol"]   = kutu(-sacak_g, -sacak_g, z_top-t, 0,         y+sacak_g, z_top)
if "sag"  in sacak_cepheler: tum["sacak_sag"]   = kutu(x,        -sacak_g, z_top-t, x+sacak_g, y+sacak_g, z_top)

# =============================================================================
# OBJ KAYDET
# =============================================================================

def brep_to_mesh(brep):
    if brep is None:
        return None
    m = rg.Mesh()
    for ms in rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.Default):
        m.Append(ms)
    return m

def sonraki_id():
    dosyalar = [f for f in os.listdir(OBJ_KLASORU) if f.endswith(".obj")]
    return len(dosyalar)

bina_id  = sonraki_id()
obj_yolu  = os.path.join(OBJ_KLASORU,  "bina_{:04d}.obj".format(bina_id))
json_yolu = os.path.join(JSON_KLASORU, "bina_{:04d}.json".format(bina_id))

obj_satirlar = ["# Mimari AI - bina_{:04d}".format(bina_id)]
vo = 0
for isim, brep in tum.items():
    if brep is None:
        continue
    m = brep_to_mesh(brep)
    if m is None:
        continue
    obj_satirlar.append("g " + isim)
    for vp in m.Vertices:
        obj_satirlar.append("v {:.4f} {:.4f} {:.4f}".format(vp.X, vp.Y, vp.Z))
    for f in m.Faces:
        if f.IsTriangle:
            obj_satirlar.append("f {} {} {}".format(f.A+vo+1, f.B+vo+1, f.C+vo+1))
        else:
            obj_satirlar.append("f {} {} {} {}".format(f.A+vo+1, f.B+vo+1, f.C+vo+1, f.D+vo+1))
    vo += m.Vertices.Count

with open(obj_yolu, "w") as f:
    f.write("\n".join(obj_satirlar))

params = {
    "bina_id": bina_id,
    "genislik": x, "derinlik": y, "yukseklik": z, "katlar": katlar,
    "kapi_cephe": kapi_cephe, "kapi_offset": kapi_offset,
    "kapi_genislik": u, "kapi_yukseklik": v_kapi,
    "pencere_cepheler": pen_cepheler,
    "pencere_genislik": pen_g, "pencere_yukseklik": pen_y,
    "pencere_deniz_seviyesi": pen_deniz,
    "cati_yukseklik": cati_yukseklik,
    "sacak_genislik": sacak_g, "sacak_cepheler": sacak_cepheler,
    "sinif_aciklamasi": {
        "0": "wall", "1": "floor", "2": "ceiling",
        "3": "door", "4": "window", "5": "roof", "6": "eave"
    }
}
with open(json_yolu, "w") as f:
    json.dump(params, f, indent=2, ensure_ascii=True)

print("Kaydedildi: bina_{:04d}  ({} eleman)".format(bina_id, len(tum)))

# =============================================================================
# GRASSHOPPER ÇIKTI (viewport önizleme)
# =============================================================================
a = [b for b in tum.values() if b is not None]

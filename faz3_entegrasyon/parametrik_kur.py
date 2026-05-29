# -*- coding: utf-8 -*-
# =============================================================================
# FAZ 3 - PARAMETRİK YENİDEN KURMA: parametrik_kur.py
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BİLEŞENİNE YAPIŞTIRILIR.
# (Rhino 7 + Grasshopper + IronPython)
#
# AMAÇ:
#   segment_v2.py herhangi bir mesh'i (Meshy AI vb.) segmentleyip
#   parametrelerini ÖLÇER. Bu bileşen o parametreleri alıp binayı
#   DÜZENLENEBİLİR bir parametrik Brep model olarak YENİDEN KURAR.
#
#   Böylece kapı genişliği slider'ını çevirince, pencere yüksekliğini
#   değiştirince... model anında güncellenir. Artık "okunan" model
#   "editlenebilir" hale gelir.
#
# AKIŞ:
#   Mesh → [segment_v2] → ölçülen parametreler → [SLIDER ile değiştir] →
#   [parametrik_kur] → editlenebilir Brep bina
#
# GRASSHOPPER BAĞLANTISI:
#   Her parametre için bir Number Slider ekle, segment_v2'nin verdiği
#   ölçülen değeri başlangıç olarak slider'a yaz, sonra istediğin gibi oyna.
#
#   GİRİŞLER (hepsi opsiyonel — boş bırakılırsa varsayılan kullanılır):
#     bina_genislik     (float)  → x ekseni
#     bina_derinlik     (float)  → y ekseni
#     kat_yuksekligi    (float)  → bir katın yüksekliği
#     kat_sayisi        (int)    → kat adedi
#     kapi_genislik     (float)
#     kapi_yukseklik    (float)
#     kapi_cephe        (str)    → "on" / "arka" / "sol" / "sag"
#     kapi_offset       (float)  → kapının cephe başından mesafesi (-1 = ortala)
#     pencere_genislik  (float)
#     pencere_yukseklik (float)
#     pencere_deniz     (float)  → pencere alt kenarının yerden yüksekliği
#     pencere_cepheler  (str)    → "on,arka,sol,sag" (virgülle)
#     cati_yukseklik    (float)  → 0 = düz çatı
#     sacak_genislik    (float)
#     sacak_cepheler    (str)    → "on,arka,sol,sag" (virgülle)
#
#   ÇIKIŞLAR:
#     a        → Brep listesi (editlenebilir bina modeli)
#     bilgi    → kullanılan parametrelerin özeti (Panel)
# =============================================================================

import Rhino.Geometry as rg

# =============================================================================
# VARSAYILAN PARAMETRELER
# Slider bağlanmazsa / boş gelirse bunlar kullanılır.
# =============================================================================

def _vars(deger, varsayilan):
    """Giriş None ya da boşsa varsayılanı döndürür."""
    try:
        if deger is None:
            return varsayilan
        return deger
    except:
        return varsayilan

x   = float(_vars(globals().get("bina_genislik"),  8.0))
y   = float(_vars(globals().get("bina_derinlik"),  6.0))
z   = float(_vars(globals().get("kat_yuksekligi"), 3.0))
kat = int(  _vars(globals().get("kat_sayisi"),     1))
t   = 0.2   # duvar kalınlığı (sabit)

u       = float(_vars(globals().get("kapi_genislik"),  1.0))
v_kapi  = float(_vars(globals().get("kapi_yukseklik"), 2.1))
kapi_cephe  = str(_vars(globals().get("kapi_cephe"),  "on")).strip().lower()
kapi_offset_giris = _vars(globals().get("kapi_offset"), -1.0)  # -1 = ortala

pen_g    = float(_vars(globals().get("pencere_genislik"),  1.2))
pen_y    = float(_vars(globals().get("pencere_yukseklik"), 1.0))
pen_deniz = float(_vars(globals().get("pencere_deniz"),    0.9))

cati_yukseklik = float(_vars(globals().get("cati_yukseklik"), 1.5))
sacak_g        = float(_vars(globals().get("sacak_genislik"), 0.4))


def _cephe_listesi(giris, varsayilan):
    """'on,arka' veya ['on','arka'] girişini temiz listeye çevirir."""
    if giris is None:
        return varsayilan
    if isinstance(giris, str):
        parcalar = [p.strip().lower() for p in giris.replace(";", ",").split(",")]
        return [p for p in parcalar if p in ("on", "arka", "sol", "sag")]
    try:
        return [str(p).strip().lower() for p in giris
                if str(p).strip().lower() in ("on", "arka", "sol", "sag")]
    except:
        return varsayilan

pen_cepheler   = _cephe_listesi(globals().get("pencere_cepheler"), ["on", "arka"])
sacak_cepheler = _cephe_listesi(globals().get("sacak_cepheler"),   ["on", "arka", "sol", "sag"])

# Güvenli sınırlar (negatif/çok büyük değerlere karşı)
x = max(2.0, x); y = max(2.0, y); z = max(2.0, z); kat = max(1, kat)
u = max(0.4, min(u, x - 0.4, y - 0.4))
v_kapi = max(1.6, min(v_kapi, z - 0.1))
pen_g = max(0.3, pen_g)
pen_y = max(0.3, pen_y)
pen_deniz = max(0.2, min(pen_deniz, z - pen_y - 0.2))

# =============================================================================
# GEOMETRİ YARDIMCILARI  (Faz 1 üreticisiyle aynı mantık)
# =============================================================================

def kutu(x0, y0, z0, x1, y1, z1):
    bb = rg.BoundingBox(rg.Point3d(x0, y0, z0), rg.Point3d(x1, y1, z1))
    return rg.Box(bb).ToBrep()


def kapi_ofset(cephe_uzunluk):
    """Kapı offset'i: -1 ise ortalar, değilse sınırlandırır."""
    if kapi_offset_giris is None or float(kapi_offset_giris) < 0:
        return max(0.2, (cephe_uzunluk - u) / 2.0)
    return max(0.2, min(float(kapi_offset_giris), cephe_uzunluk - u - 0.2))


def pen_ofset(cephe_uzunluk):
    """Pencereyi cephede ortalar."""
    return max(0.2, (cephe_uzunluk - pen_g) / 2.0)


def on_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_ofset(x)
        p["kapi_sol"] = kutu(0,    0, zb, ko,    t, zb + zh)
        p["kapi_sag"] = kutu(ko+u, 0, zb, x,     t, zb + zh)
        p["kapi_ust"] = kutu(ko,   0, zb + v_kapi, ko + u, t, zb + zh)
    elif pen:
        po = pen_ofset(x)
        p["pen_sol"] = kutu(0,        0, zb,                  po,       t, zb + zh)
        p["pen_sag"] = kutu(po+pen_g, 0, zb,                  x,        t, zb + zh)
        p["pen_alt"] = kutu(po,       0, zb,                  po+pen_g, t, zb + pen_deniz)
        p["pen_ust"] = kutu(po,       0, zb+pen_deniz+pen_y,  po+pen_g, t, zb + zh)
    else:
        p["duvar"] = kutu(0, 0, zb, x, t, zb + zh)
    return p


def arka_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_ofset(x)
        p["kapi_sol"] = kutu(0,    y-t, zb, ko,    y, zb + zh)
        p["kapi_sag"] = kutu(ko+u, y-t, zb, x,     y, zb + zh)
        p["kapi_ust"] = kutu(ko,   y-t, zb + v_kapi, ko + u, y, zb + zh)
    elif pen:
        po = pen_ofset(x)
        p["pen_sol"] = kutu(0,        y-t, zb,                  po,       y, zb + zh)
        p["pen_sag"] = kutu(po+pen_g, y-t, zb,                  x,        y, zb + zh)
        p["pen_alt"] = kutu(po,       y-t, zb,                  po+pen_g, y, zb + pen_deniz)
        p["pen_ust"] = kutu(po,       y-t, zb+pen_deniz+pen_y,  po+pen_g, y, zb + zh)
    else:
        p["duvar"] = kutu(0, y-t, zb, x, y, zb + zh)
    return p


def sol_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_ofset(y)
        p["kapi_sol"] = kutu(0, 0,    zb, t, ko,    zb + zh)
        p["kapi_sag"] = kutu(0, ko+u, zb, t, y,     zb + zh)
        p["kapi_ust"] = kutu(0, ko,   zb + v_kapi, t, ko + u, zb + zh)
    elif pen:
        po = pen_ofset(y)
        p["pen_sol"] = kutu(0, 0,        zb,                  t, po,       zb + zh)
        p["pen_sag"] = kutu(0, po+pen_g, zb,                  t, y,        zb + zh)
        p["pen_alt"] = kutu(0, po,       zb,                  t, po+pen_g, zb + pen_deniz)
        p["pen_ust"] = kutu(0, po,       zb+pen_deniz+pen_y,  t, po+pen_g, zb + zh)
    else:
        p["duvar"] = kutu(0, 0, zb, t, y, zb + zh)
    return p


def sag_duvar(zb, zh, kapi=False, pen=False):
    p = {}
    if kapi:
        ko = kapi_ofset(y)
        p["kapi_sol"] = kutu(x-t, 0,    zb, x, ko,    zb + zh)
        p["kapi_sag"] = kutu(x-t, ko+u, zb, x, y,     zb + zh)
        p["kapi_ust"] = kutu(x-t, ko,   zb + v_kapi, x, ko + u, zb + zh)
    elif pen:
        po = pen_ofset(y)
        p["pen_sol"] = kutu(x-t, 0,        zb,                  x, po,       zb + zh)
        p["pen_sag"] = kutu(x-t, po+pen_g, zb,                  x, y,        zb + zh)
        p["pen_alt"] = kutu(x-t, po,       zb,                  x, po+pen_g, zb + pen_deniz)
        p["pen_ust"] = kutu(x-t, po,       zb+pen_deniz+pen_y,  x, po+pen_g, zb + zh)
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

# =============================================================================
# MODELİ KUR
# =============================================================================

tum = {}
for k in range(kat):
    tum.update(kat_uret(k))

z_top = kat * z

# Çatı (cati_yukseklik > 0 ise beşik, değilse düz kapak)
if cati_yukseklik > 0.05:
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
else:
    tum["cati_duz"] = kutu(0, 0, z_top, x, y, z_top + t)

# Saçaklar
if sacak_g > 0.01:
    if "on"   in sacak_cepheler: tum["sacak_on"]   = kutu(-sacak_g, -sacak_g, z_top-t, x+sacak_g, 0,         z_top)
    if "arka" in sacak_cepheler: tum["sacak_arka"] = kutu(-sacak_g, y,        z_top-t, x+sacak_g, y+sacak_g, z_top)
    if "sol"  in sacak_cepheler: tum["sacak_sol"]  = kutu(-sacak_g, -sacak_g, z_top-t, 0,         y+sacak_g, z_top)
    if "sag"  in sacak_cepheler: tum["sacak_sag"]  = kutu(x,        -sacak_g, z_top-t, x+sacak_g, y+sacak_g, z_top)

# =============================================================================
# GRASSHOPPER ÇIKTI
# =============================================================================

a = [b for b in tum.values() if b is not None]

bilgi = "\n".join([
    "=== YENIDEN KURULAN PARAMETRIK MODEL ===",
    "Bina: {:.2f} x {:.2f} m, kat yuk {:.2f} m x {} kat".format(x, y, z, kat),
    "Kapi: {:.2f} x {:.2f} m  cephe={}".format(u, v_kapi, kapi_cephe),
    "Pencere: {:.2f} x {:.2f} m  denizlik {:.2f} m  cepheler={}".format(
        pen_g, pen_y, pen_deniz, ",".join(pen_cepheler) if pen_cepheler else "yok"),
    "Cati yuksekligi: {:.2f} m {}".format(cati_yukseklik, "(duz)" if cati_yukseklik <= 0.05 else "(besik)"),
    "Sacak: {:.2f} m  cepheler={}".format(sacak_g, ",".join(sacak_cepheler) if sacak_cepheler else "yok"),
    "Toplam eleman: {}".format(len(a)),
    "",
    ">> Her parametreye bir Number Slider bagla, modeli editle.",
])

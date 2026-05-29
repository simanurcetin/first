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
#   "parametre_json" çıkışında yapısal veriyi verir:
#     - bina boyutları, kat sayısı, çatı yüksekliği
#     - her açıklığın (pencere/kapı) CEPHESİ + KONUMU + BOYUTU
#
#   Bu bileşen o JSON'u okuyup binayı DÜZENLENEBİLİR bir parametrik
#   Brep model olarak YENİDEN KURAR — pencereler/kapılar GERÇEK
#   yerlerinde, doğru sayıda. Yani "import ettiğin bina, ama artık
#   editlenebilir". Slider'larla rötuş yaparsın.
#
# AKIŞ:
#   Mesh → [segment_v2] → parametre_json → [parametrik_kur] → editlenebilir bina
#                                              ↑ slider'lar (global rötuş)
#
# GRASSHOPPER GİRİŞLERİ (hepsi opsiyonel):
#   parametre_json   (str)  → segment_v2'nin "parametre_json" çıkışını bağla
#
#   --- EDITLEME ÇARPANLARI (slider) — hepsi 1.0'da "olculen gibi, degisme" ---
#   --- ASLA mutlak metre girmezsin; sadece carpani oynatirsin ---
#   genislik_olcek        (float)  1.0 = ayni,  1.2 = %20 genis
#   derinlik_olcek        (float)  1.0 = ayni
#   kat_yuksekligi_olcek  (float)  1.0 = ayni
#   cati_olcek            (float)  1.0 = ayni,  0 = duz cati
#   pencere_olcek         (float)  1.0 = ayni,  pencereleri buyut/kucult
#   kapi_olcek            (float)  1.0 = ayni,  kapilari buyut/kucult
#   kat_ekle              (int)    0 = ayni,  +1 = bir kat ekle, -1 = cikar
#   sacak_genislik        (float)  mutlak, 0 = sacak yok
#
# ÇIKIŞLAR:
#   a       → Brep listesi (editlenebilir bina modeli)
#   bilgi   → ölçülen → editlenen değerlerin özeti (Panel)
# =============================================================================

import Rhino.Geometry as rg
import json


def _vars(deger, varsayilan):
    """Giriş None / boş ise varsayılanı döndürür."""
    try:
        if deger is None:
            return varsayilan
        if isinstance(deger, str) and deger.strip() == "":
            return varsayilan
        return deger
    except:
        return varsayilan

# --- segment_v2'den gelen JSON'u oku ---
_json = _vars(globals().get("parametre_json"), "")
veri = {}
if _json:
    try:
        veri = json.loads(_json)
    except:
        veri = {}

# --- TEMEL DEĞERLER: segment_v2 JSON'dan otomatik gelir (elle girilmez!) ---
b_genislik = float(veri.get("genislik",       8.0))
b_derinlik = float(veri.get("derinlik",       6.0))
b_kat_yuk  = float(veri.get("kat_yuksekligi", 3.0))
b_kat      = int(round(float(veri.get("kat_sayisi", 1))))
b_cati     = float(veri.get("cati_yukseklik", 1.5))

# --- EDITLEME ÇARPANLARI: hepsi 1.0'da = "olculen gibi, degisme" ---
# Asla mutlak deger yazmazsin; sadece carpani oynatirsin.
genislik_olcek       = float(_vars(globals().get("genislik_olcek"),       1.0))
derinlik_olcek       = float(_vars(globals().get("derinlik_olcek"),       1.0))
kat_yuksekligi_olcek = float(_vars(globals().get("kat_yuksekligi_olcek"), 1.0))
cati_olcek           = float(_vars(globals().get("cati_olcek"),           1.0))
pen_olcek            = float(_vars(globals().get("pencere_olcek"),        1.0))
kapi_olcek           = float(_vars(globals().get("kapi_olcek"),           1.0))
kat_ekle             = int(  _vars(globals().get("kat_ekle"),             0))   # +1/-1 kat
sacak_g              = float(_vars(globals().get("sacak_genislik"),       0.0)) # mutlak (varsayilan yok)

# --- Son değerler: olculen × carpan ---
x   = max(2.0, b_genislik * genislik_olcek)
y   = max(2.0, b_derinlik * derinlik_olcek)
z   = max(2.0, b_kat_yuk  * kat_yuksekligi_olcek)
kat = max(1,   b_kat + kat_ekle)
cati_yukseklik = max(0.0, b_cati * cati_olcek)
t = 0.2   # duvar kalınlığı

acikliklar = veri.get("acikliklar", [])

# =============================================================================
# GEOMETRİ YARDIMCILARI
# =============================================================================

def kutu(x0, y0, z0, x1, y1, z1):
    bb = rg.BoundingBox(rg.Point3d(x0, y0, z0), rg.Point3d(x1, y1, z1))
    return rg.Box(bb).ToBrep()


def bool_fark(brep, kesiciler, tol=0.001):
    """Duvardan açıklıkları çıkarır. Başarısız olursa solid duvarı döndürür."""
    if not kesiciler:
        return [brep]
    try:
        sonuc = rg.Brep.CreateBooleanDifference([brep], list(kesiciler), tol)
        if sonuc and len(sonuc) > 0:
            return list(sonuc)
    except:
        pass
    return [brep]

# =============================================================================
# MODELİ KUR
# =============================================================================

tum = {}
wall_h = kat * z   # duvarların toplam yüksekliği

# Döşeme + tavan (her kat)
for k in range(kat):
    zb = k * z
    tum["zemin_{}".format(k)] = kutu(0, 0, zb,        x, y, zb + t)
    tum["tavan_{}".format(k)] = kutu(0, 0, zb + z - t, x, y, zb + z)

# Solid duvar panelleri (4 cephe)
duvarlar = {
    "on":   kutu(0,     0,     0, x,   t,   wall_h),
    "arka": kutu(0,     y - t, 0, x,   y,   wall_h),
    "sol":  kutu(0,     0,     0, t,   y,   wall_h),
    "sag":  kutu(x - t, 0,     0, x,   y,   wall_h),
}

# Açıklıkları cepheye göre grupla → kesici kutular + dolgu panelleri
kesiciler = {"on": [], "arka": [], "sol": [], "sag": []}
paneller = []

for ac in acikliklar:
    cephe = ac.get("cephe", "on")
    if cephe not in kesiciler:
        continue
    u = float(ac.get("u", 0.5))
    v = float(ac.get("v_alt", 0.9))
    g = float(ac.get("genislik", 1.0))
    h = float(ac.get("yukseklik", 1.0))

    # Global ölçek (pencere/kapı)
    olcek = pen_olcek if ac.get("tip") == "pencere" else kapi_olcek
    gc = max(0.3, g * olcek)
    hc = max(0.3, h * olcek)
    u = u - (gc - g) / 2.0   # ölçeği merkezden uygula

    # Cephe uzunluğuna göre konumu sınırla
    cephe_uz = x if cephe in ("on", "arka") else y
    if cephe_uz - gc - 0.1 > 0.1:
        u = max(0.1, min(u, cephe_uz - gc - 0.1))
    else:
        u = 0.1
    if v + hc > wall_h:
        hc = max(0.3, wall_h - v - 0.05)

    # Cepheye göre kesici (duvarı tam deler) + ince dolgu paneli
    if cephe == "on":
        kesiciler["on"].append(kutu(u, -0.1, v, u + gc, t + 0.1, v + hc))
        paneller.append(kutu(u, t * 0.4, v, u + gc, t * 0.6, v + hc))
    elif cephe == "arka":
        kesiciler["arka"].append(kutu(u, y - t - 0.1, v, u + gc, y + 0.1, v + hc))
        paneller.append(kutu(u, y - t * 0.6, v, u + gc, y - t * 0.4, v + hc))
    elif cephe == "sol":
        kesiciler["sol"].append(kutu(-0.1, u, v, t + 0.1, u + gc, v + hc))
        paneller.append(kutu(t * 0.4, u, v, t * 0.6, u + gc, v + hc))
    else:  # sag
        kesiciler["sag"].append(kutu(x - t - 0.1, u, v, x + 0.1, u + gc, v + hc))
        paneller.append(kutu(x - t * 0.6, u, v, x - t * 0.4, u + gc, v + hc))

# Duvarları açıklıklarla del
duvar_breps = []
for cephe, brep in duvarlar.items():
    duvar_breps += bool_fark(brep, kesiciler[cephe])

# Çatı
cati_breps = []
if cati_yukseklik > 0.05:
    p0 = rg.Point3d(0,   0, wall_h);  p1 = rg.Point3d(x,   0, wall_h)
    p2 = rg.Point3d(x,   y, wall_h);  p3 = rg.Point3d(0,   y, wall_h)
    p4 = rg.Point3d(x/2, 0, wall_h + cati_yukseklik)
    p5 = rg.Point3d(x/2, y, wall_h + cati_yukseklik)
    for pts in [(p0, p4, p5, p3), (p4, p1, p2, p5), (p0, p1, p4, p4), (p3, p5, p2, p2)]:
        b = rg.Brep.CreateFromCornerPoints(pts[0], pts[1], pts[2], pts[3], 0.01)
        if b:
            cati_breps.append(b)
else:
    cati_breps.append(kutu(0, 0, wall_h, x, y, wall_h + t))

# Saçak (opsiyonel)
if sacak_g > 0.01:
    cati_breps.append(kutu(-sacak_g, -sacak_g, wall_h - t, x + sacak_g, y + sacak_g, wall_h))

# =============================================================================
# GRASSHOPPER ÇIKTI
# =============================================================================

a = (list(tum.values()) + duvar_breps + paneller + cati_breps)
a = [b for b in a if b is not None]

n_pen = sum(1 for ac in acikliklar if ac.get("tip") == "pencere")
n_kapi = sum(1 for ac in acikliklar if ac.get("tip") == "kapi")

bilgi = "\n".join([
    "=== YENIDEN KURULAN PARAMETRIK MODEL ===",
    "Kaynak: {}".format("segment_v2 JSON" if veri else "varsayilan"),
    "Olculen -> Editlenen:",
    "  Genislik: {:.2f} -> {:.2f} m  (x{:.2f})".format(b_genislik, x, genislik_olcek),
    "  Derinlik: {:.2f} -> {:.2f} m  (x{:.2f})".format(b_derinlik, y, derinlik_olcek),
    "  Kat yuk:  {:.2f} -> {:.2f} m  (x{:.2f})".format(b_kat_yuk, z, kat_yuksekligi_olcek),
    "  Kat sayi: {} -> {}  (+{})".format(b_kat, kat, kat_ekle),
    "  Cati:     {:.2f} -> {:.2f} m  (x{:.2f})".format(b_cati, cati_yukseklik, cati_olcek),
    "Pencere: {} (x{:.2f})   Kapi: {} (x{:.2f})  [gercek konumlarda]".format(
        n_pen, pen_olcek, n_kapi, kapi_olcek),
    "Toplam eleman: {}".format(len(a)),
    "",
    ">> TUM carpanlar 1.0 = olculen gibi. Oynat = editle. Mutlak deger GIRME.",
])

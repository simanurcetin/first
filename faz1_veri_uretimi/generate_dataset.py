# -*- coding: utf-8 -*-
# =============================================================================
# FAZ 1 - STANDALONE SENTETIK BINA URETICISI (Rhino GEREKMEZ)
# =============================================================================
#
# Onceki grasshopper_generate.py tik basina 1 bina uretiyordu. Bu surum saf
# Python ile calisir; tek komutla binlerce OBJ yazar. Binalar eksen-hizali
# kutulardan olustugundan Rhino'nun mesh'leyicisine ihtiyac yoktur.
#
# YENI SPESIFIKASYON (v3):
#   - Tek katli (katlar = 1)
#   - 4 duvar
#   - Tam 1 kapi (rastgele bir cephede)
#   - Tam 2 pencere (kapi olmayan 2 cephede) - konum & boyut bagimsiz degisken
#   - Cati + sacak: onceki mantik aynen korunur (etiketler degismez)
#
# OBJ grup adlari -> sinif etiketleri (01_obj_to_pointcloud.py okur):
#   zemin_* -> 1 (floor)   tavan_* -> 2 (ceiling)   *duvar -> 0 (wall)
#   *kapi*  -> 3 (door)    *pen_*  -> 4 (window)     cati_* -> 5 (roof)
#   sacak_* -> 6 (eave)
#
# CIKTI:
#   data_v3/train_obj/  (5000 obj)
#   data_v3/test_obj/   (500  obj)
# Train ve test bagimsiz rastgele uretildiginden ayrim dogal olarak temizdir
# (test binalari train'in kopyasi degil, yeni orneklerdir).
#
# CALISTIRMA:
#   python faz1_veri_uretimi/generate_dataset.py
#   (istege bagli)  python faz1_veri_uretimi/generate_dataset.py 5000 500
# =============================================================================

import os
import sys
import random

# ── Ayarlar ───────────────────────────────────────────────────
TRAIN_ADET = 5000
TEST_ADET  = 500
TRAIN_KLASOR = "data_v3/train_obj"
TEST_KLASOR  = "data_v3/test_obj"
SEED = 42
T = 0.2   # duvar/doseme kalinligi

if len(sys.argv) >= 2:
    TRAIN_ADET = int(sys.argv[1])
if len(sys.argv) >= 3:
    TEST_ADET = int(sys.argv[2])

CEPHELER = ["on", "arka", "sol", "sag"]


# ── OBJ yazim yardimcilari ────────────────────────────────────

def add_box(lines, state, name, x0, y0, z0, x1, y1, z1):
    """Bir kutuyu (8 kose, 6 dortgen yuzey, disa donuk normaller) ekler."""
    lines.append("g " + name)
    verts = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    for (px, py, pz) in verts:
        lines.append("v %.4f %.4f %.4f" % (px, py, pz))
    o = state[0]
    # Disa donuk sarim: alt(-z), ust(+z), on(-y), arka(+y), sol(-x), sag(+x)
    quads = [
        (0, 3, 2, 1), (4, 5, 6, 7),
        (0, 1, 5, 4), (3, 7, 6, 2),
        (0, 4, 7, 3), (1, 2, 6, 5),
    ]
    for q in quads:
        lines.append("f %d %d %d %d" % (o+q[0]+1, o+q[1]+1, o+q[2]+1, o+q[3]+1))
    state[0] += 8


def add_poly(lines, state, name, pts):
    """Tek bir cokgen yuzey (ucgen/dortgen) ekler - cati parcalari icin."""
    lines.append("g " + name)
    for (px, py, pz) in pts:
        lines.append("v %.4f %.4f %.4f" % (px, py, pz))
    o = state[0]
    idx = " ".join(str(o+i+1) for i in range(len(pts)))
    lines.append("f " + idx)
    state[0] += len(pts)


# ── Duvar parcalari (cepheye ve tipe gore kutu koordinatlari) ──

def duvar_kutulari(cephe, tip, zb, zh, x, y, wp):
    """
    Bir cephenin duvar parcalarini (suffix, (x0,y0,z0,x1,y1,z1)) listesi olarak
    dondurur. tip: 'duvar' | 'kapi' | 'pen'. wp: acinim parametreleri dict.
    """
    kutular = []
    if cephe == "on":       yb0, yb1 = 0.0, T
    elif cephe == "arka":   yb0, yb1 = y - T, y
    elif cephe == "sol":    xb0, xb1 = 0.0, T
    else:                   xb0, xb1 = x - T, x

    # yatay eksen uzunlugu (kapi/pencere bu eksen boyunca yerlesir)
    L = x if cephe in ("on", "arka") else y

    def yatay_kutu(a0, a1, z0, z1):
        # a0..a1 = cephenin yatay ekseni boyunca; kalinlik yonu sabit
        if cephe in ("on", "arka"):
            return (a0, yb0, z0, a1, yb1, z1)
        else:
            return (xb0, a0, z0, xb1, a1, z1)

    if tip == "kapi":
        ko = wp["offset"]; u = wp["u"]; vk = wp["v_kapi"]
        kutular.append(("kapi_sol", yatay_kutu(0.0,   ko,    zb,      zb + zh)))
        kutular.append(("kapi_sag", yatay_kutu(ko + u, L,    zb,      zb + zh)))
        kutular.append(("kapi_ust", yatay_kutu(ko,    ko + u, zb + vk, zb + zh)))
    elif tip == "pen":
        po = wp["po"]; g = wp["g"]; yy = wp["y"]; dz = wp["deniz"]
        kutular.append(("pen_sol", yatay_kutu(0.0,    po,     zb,          zb + zh)))
        kutular.append(("pen_sag", yatay_kutu(po + g, L,      zb,          zb + zh)))
        kutular.append(("pen_alt", yatay_kutu(po,     po + g, zb,          zb + dz)))
        kutular.append(("pen_ust", yatay_kutu(po,     po + g, zb + dz + yy, zb + zh)))
    else:  # duz duvar
        kutular.append(("duvar", yatay_kutu(0.0, L, zb, zb + zh)))
    return kutular


# ── Tek bina uret ─────────────────────────────────────────────

def bina_uret(rng, bina_id):
    lines = ["# Mimari AI v3 - bina_%04d" % bina_id]
    state = [0]   # global vertex offset (list = mutable)

    # Bina boyutlari (tek kat)
    x = round(rng.uniform(4.0, 10.0), 2)
    y = round(rng.uniform(4.0, 10.0), 2)
    z = round(rng.uniform(2.4, 3.5), 2)
    zb = 0.0

    # Kapi: rastgele bir cephe
    kapi_cephe = rng.choice(CEPHELER)
    L_kapi = x if kapi_cephe in ("on", "arka") else y
    u = round(rng.uniform(0.8, min(1.2, L_kapi / 3.0)), 2)
    v_kapi = round(rng.uniform(2.0, min(2.4, z - 0.2)), 2)
    kapi_offset = round(rng.uniform(0.3, max(0.31, L_kapi - u - 0.3)), 2)
    kapi_wp = {"offset": kapi_offset, "u": u, "v_kapi": v_kapi}

    # Pencereler: kapi olmayan 3 cepheden 2'si (her biri bagimsiz konum/boyut)
    kalan = [c for c in CEPHELER if c != kapi_cephe]
    pen_cepheler = rng.sample(kalan, 2)
    pen_wp = {}
    for c in pen_cepheler:
        L = x if c in ("on", "arka") else y
        g = round(rng.uniform(0.6, min(1.5, L / 3.0)), 2)
        yy = round(rng.uniform(0.6, 1.0), 2)
        deniz = round(rng.uniform(0.7, 1.0), 2)
        po = round(rng.uniform(0.3, max(0.31, L - g - 0.3)), 2)
        pen_wp[c] = {"po": po, "g": g, "y": yy, "deniz": deniz}

    # Doseme + tavan
    add_box(lines, state, "zemin_0", 0, 0, zb,        x, y, zb + T)
    add_box(lines, state, "tavan_0", 0, 0, zb + z - T, x, y, zb + z)

    # Duvarlar
    for cephe in CEPHELER:
        if cephe == kapi_cephe:
            tip, wp = "kapi", kapi_wp
        elif cephe in pen_cepheler:
            tip, wp = "pen", pen_wp[cephe]
        else:
            tip, wp = "duvar", None
        for suffix, (bx0, by0, bz0, bx1, by1, bz1) in \
                duvar_kutulari(cephe, tip, zb, z, x, y, wp):
            ad = "%s_0_%s" % (cephe, suffix)
            add_box(lines, state, ad, bx0, by0, bz0, bx1, by1, bz1)

    # Cati (onceki mantik: besik cati, 2 dortgen egim + 2 ucgen alinlik)
    z_top = z
    ch = round(rng.uniform(1.0, 2.0), 2)
    p0 = (0, 0, z_top); p1 = (x, 0, z_top); p2 = (x, y, z_top); p3 = (0, y, z_top)
    p4 = (x/2.0, 0, z_top + ch); p5 = (x/2.0, y, z_top + ch)
    add_poly(lines, state, "cati_sol",  [p0, p4, p5, p3])
    add_poly(lines, state, "cati_sag",  [p4, p1, p2, p5])
    add_poly(lines, state, "cati_on",   [p0, p1, p4])
    add_poly(lines, state, "cati_arka", [p3, p5, p2])

    # Sacak (onceki mantik: rastgele cephelerde)
    sg = round(rng.uniform(0.2, 0.6), 2)
    sacak_cepheler = rng.sample(CEPHELER, rng.randint(1, 4))
    if "on" in sacak_cepheler:
        add_box(lines, state, "sacak_on",   -sg, -sg, z_top - T, x + sg, 0,      z_top)
    if "arka" in sacak_cepheler:
        add_box(lines, state, "sacak_arka", -sg, y,   z_top - T, x + sg, y + sg, z_top)
    if "sol" in sacak_cepheler:
        add_box(lines, state, "sacak_sol",  -sg, -sg, z_top - T, 0,      y + sg, z_top)
    if "sag" in sacak_cepheler:
        add_box(lines, state, "sacak_sag",   x,  -sg, z_top - T, x + sg, y + sg, z_top)

    return "\n".join(lines)


def klasor_uret(klasor, adet, rng, etiket):
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    for i in range(adet):
        obj = bina_uret(rng, i)
        with open(os.path.join(klasor, "bina_%04d.obj" % i), "w") as f:
            f.write(obj)
        if (i + 1) % 500 == 0:
            print("  %s: %d/%d" % (etiket, i + 1, adet))
    print("  %s TAMAM: %d bina -> %s" % (etiket, adet, klasor))


def main():
    rng = random.Random(SEED)
    print("=" * 55)
    print("  SENTETIK BINA URETIMI (v3) - tek kat, 1 kapi, 2 pencere")
    print("  Train: %d   Test: %d" % (TRAIN_ADET, TEST_ADET))
    print("=" * 55)
    klasor_uret(TRAIN_KLASOR, TRAIN_ADET, rng, "TRAIN")
    klasor_uret(TEST_KLASOR,  TEST_ADET,  rng, "TEST")
    print("\nTamam! Train ve test bagimsiz uretildi (temiz ayrim).")


if __name__ == "__main__":
    main()

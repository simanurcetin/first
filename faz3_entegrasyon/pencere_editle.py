# -*- coding: utf-8 -*-
# =============================================================================
# FAZ 3 - PROGRAM 2: pencere_editle.py
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BILESENINE YAPISTIRILIR.
# (Rhino 7 + Grasshopper + IronPython)
#
# AMAC:
#   segment_v2.py'nin (Program 1) cikardigi SEGMENTE mesh'i alir ve
#   ORIJINAL GEOMETRIYI KORUYARAK sadece "pencere" etiketli yuzlerin
#   verteksLerini number slider ile buyutur/kucultur.
#
#   parametrik_kur.py gibi SIFIRDAN kutu insa ETMEZ. Meshy AI'dan gelen
#   gercek bina oldugu gibi kalir; yalnizca pencereler degisir.
#
# AKIS:
#   OBJ -> [Program1 segment_v2] -> a (mesh) + siniflar
#                                       |  + pen_genislik (slider)
#                                       |  + pen_yukseklik (slider)
#                                       v
#                                 [Program2 pencere_editle] -> editlenmis mesh
#                                       v
#                                 [Program3 mesh_to_obj] -> guncellenmis.obj
#
# GRASSHOPPER GIRISLERI:
#   mesh_in       (Mesh)   -> Program1'in "a" cikisi
#   siniflar      (list)   -> Program1'in "siniflar" cikisi (yuz basina 1 int)
#   pen_genislik  (float)  -> Number Slider  Min 0.5 / Max 2.0 / Value 1.0
#   pen_yukseklik (float)  -> Number Slider  Min 0.5 / Max 2.0 / Value 1.0
#
# CIKISLAR:
#   a      -> editlenmis mesh (Rhino viewport'ta gorunur)
#   bilgi  -> ozet (Panel)
# =============================================================================

import Rhino.Geometry as rg

PENCERE = 4   # pencere sinif no (0=duvar 1=zemin 2=tavan 3=kapi 4=pencere 5=cati 6=sacak)


def _v(d, x):
    return x if d is None else d


fw = float(_v(globals().get("pen_genislik"),  1.0))   # 1.0 = ayni
fh = float(_v(globals().get("pen_yukseklik"), 1.0))   # 1.0 = ayni

a = None
bilgi = "mesh_in + siniflar baglayin (Program1'in a ve siniflar cikislari)."

if ("mesh_in" in dir() and mesh_in is not None
        and "siniflar" in dir() and siniflar):

    mesh = mesh_in.DuplicateMesh()
    F = mesh.Faces
    V = mesh.Vertices

    def yuz_vtx(i):
        f = F[i]
        return [f.A, f.B, f.C] if f.IsTriangle else [f.A, f.B, f.C, f.D]

    # 1) Pencere yuzleri
    pen_yuz = [i for i in range(F.Count)
               if i < len(siniflar) and siniflar[i] == PENCERE]

    # 2) Ortak vertex paylasan pencere yuzlerini kumele = ayri ayri pencereler
    vtx_face = {}
    for i in pen_yuz:
        for vi in yuz_vtx(i):
            vtx_face.setdefault(vi, []).append(i)

    ziyaret = set()
    kumeler = []
    for bas in pen_yuz:
        if bas in ziyaret:
            continue
        yigin = [bas]
        ziyaret.add(bas)
        kume = []
        while yigin:
            f = yigin.pop()
            kume.append(f)
            for vi in yuz_vtx(f):
                for k in vtx_face.get(vi, []):
                    if k not in ziyaret:
                        ziyaret.add(k)
                        yigin.append(k)
        kumeler.append(kume)

    # 3) Her pencereyi kendi merkezinden olcekle
    for kume in kumeler:
        vset = set()
        for f in kume:
            for vi in yuz_vtx(f):
                vset.add(vi)
        vlist = list(vset)
        if len(vlist) < 3:
            continue

        xs = [V[vi].X for vi in vlist]
        ys = [V[vi].Y for vi in vlist]
        zs = [V[vi].Z for vi in vlist]
        cx = sum(xs) / len(xs)
        cy = sum(ys) / len(ys)
        cz = sum(zs) / len(zs)

        # Cephe yonu: hangi yatay eksende daha genis yayilmis?
        #   on/arka cephe -> X'te genis    sol/sag cephe -> Y'de genis
        yatay_x = (max(xs) - min(xs)) >= (max(ys) - min(ys))

        for vi in vlist:
            p = V[vi]
            nx, ny, nz = p.X, p.Y, p.Z
            if yatay_x:
                nx = cx + (p.X - cx) * fw   # yatay = X
            else:
                ny = cy + (p.Y - cy) * fw   # yatay = Y
            nz = cz + (p.Z - cz) * fh       # yukseklik her zaman Z
            V.SetVertex(vi, nx, ny, nz)

    mesh.Normals.ComputeNormals()
    mesh.Compact()
    a = mesh

    bilgi = "\n".join([
        "=== PENCERE EDIT (orijinal mesh korundu) ===",
        "Pencere yuzu: {}".format(len(pen_yuz)),
        "Bulunan pencere sayisi: {}".format(len(kumeler)),
        "Genislik carpani: x{:.2f}".format(fw),
        "Yukseklik carpani: x{:.2f}".format(fh),
        "",
        ">> 1.0 = orijinal. Slider oynat = pencere boyutu degisir.",
        ">> Cok buyuk carpanda pencere duvar deliginden tasabilir.",
    ])

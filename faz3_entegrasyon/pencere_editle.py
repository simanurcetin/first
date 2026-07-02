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
import Rhino
import math

PENCERE = 4   # pencere sinif no (0=duvar 1=zemin 2=tavan 3=kapi 4=pencere 5=cati 6=sacak)


def _v(d, x):
    return x if d is None else d


def mesh_coerce(m):
    """Giris gercek Mesh degilse (GUID / Brep) onu gercek Mesh'e cevirir."""
    if m is None:
        return None
    if isinstance(m, rg.Mesh):
        return m
    # Brep/Extrusion -> Mesh
    try:
        brep = m if isinstance(m, rg.Brep) else m.ToBrep()
        if brep is not None:
            birlesik = rg.Mesh()
            parcalar = rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.Default)
            if parcalar:
                for ms in parcalar:
                    birlesik.Append(ms)
            if birlesik.Faces.Count > 0:
                return birlesik
    except:
        pass
    # GUID -> Rhino dokumanindan getir
    try:
        import System
        if isinstance(m, System.Guid):
            doc = Rhino.RhinoDoc.ActiveDoc
            obj = doc.Objects.FindId(m)
            if obj is not None and isinstance(obj.Geometry, rg.Mesh):
                return obj.Geometry
    except:
        pass
    return m


fw = float(_v(globals().get("pen_genislik"),  1.0))   # 1.0 = ayni
fh = float(_v(globals().get("pen_yukseklik"), 1.0))   # 1.0 = ayni

a = None
bilgi = "mesh_in + siniflar baglayin (Program1'in a ve siniflar cikislari)."

if ("mesh_in" in dir() and mesh_in is not None
        and "siniflar" in dir() and siniflar):

    mesh_in = mesh_coerce(mesh_in)
    mesh = mesh_in.DuplicateMesh()
    F = mesh.Faces
    V = mesh.Vertices

    def yuz_vtx(i):
        f = F[i]
        return [f.A, f.B, f.C] if f.IsTriangle else [f.A, f.B, f.C, f.D]

    # 1) Pencere yuzleri
    pen_yuz = [i for i in range(F.Count)
               if i < len(siniflar) and siniflar[i] == PENCERE]

    # Her pencere yuzunun merkezi
    def yuz_merkez(i):
        vs = yuz_vtx(i)
        n = len(vs)
        return (sum(V[vi].X for vi in vs) / n,
                sum(V[vi].Y for vi in vs) / n,
                sum(V[vi].Z for vi in vs) / n)

    merkez = {}
    for i in pen_yuz:
        merkez[i] = yuz_merkez(i)

    # Esik: pencere yuzlerinin ortalama kenar uzunlugu x 2.5
    # (Meshy mesh'i unwelded oldugu icin vertex numarasi yerine
    #  KONUM yakinligina gore kumeliyoruz.)
    toplam_kenar = 0.0
    kenar_say = 0
    for i in pen_yuz:
        vs = yuz_vtx(i)
        m = len(vs)
        for k in range(m):
            p1 = V[vs[k]]
            p2 = V[vs[(k + 1) % m]]
            toplam_kenar += math.sqrt((p1.X - p2.X) ** 2 +
                                      (p1.Y - p2.Y) ** 2 +
                                      (p1.Z - p2.Z) ** 2)
            kenar_say += 1
    ort_kenar = (toplam_kenar / kenar_say) if kenar_say > 0 else 1.0
    esik = ort_kenar * 2.5

    def uzaklik(a1, b1):
        return math.sqrt((a1[0] - b1[0]) ** 2 +
                         (a1[1] - b1[1]) ** 2 +
                         (a1[2] - b1[2]) ** 2)

    # 2) KONUM yakinligina gore kumele = birbirine degen ucgenler = tek pencere
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
            cf = merkez[f]
            for k in pen_yuz:
                if k in ziyaret:
                    continue
                if uzaklik(cf, merkez[k]) < esik:
                    ziyaret.add(k)
                    yigin.append(k)
        kumeler.append(kume)

    # Gurultu filtresi: tek/cok kucuk kumeler (1-2 ucgen) gercek pencere degil
    kumeler = [k for k in kumeler if len(k) >= 3]

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
        "Bulunan pencere sayisi: {}  (konum yakinligina gore)".format(len(kumeler)),
        "Kumeleme esigi: {:.3f} m".format(esik),
        "Genislik carpani: x{:.2f}".format(fw),
        "Yukseklik carpani: x{:.2f}".format(fh),
        "",
        ">> 1.0 = orijinal. Slider oynat = pencere boyutu degisir.",
        ">> Cok buyuk carpanda pencere duvar deliginden tasabilir.",
    ])

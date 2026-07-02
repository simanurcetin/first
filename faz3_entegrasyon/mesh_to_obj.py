# -*- coding: utf-8 -*-
# =============================================================================
# FAZ 3 - PROGRAM 3: mesh_to_obj.py
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BILESENINE YAPISTIRILIR.
# (Rhino 7 + Grasshopper + IronPython)
#
# AMAC:
#   Program2'nin (pencere_editle) editledigi mesh'i diske OBJ dosyasi
#   olarak yazar. Mesh cikisi ayni zamanda Rhino viewport'ta gorunur.
#
# GRASSHOPPER GIRISLERI:
#   mesh_in     (Mesh)  -> Program2'nin "a" cikisi
#   dosya_yolu  (str)   -> kayit yolu (bos birakilirsa varsayilan kullanilir)
#   yaz         (bool)  -> Boolean Toggle. True = dosyaya yaz
#
# CIKISLAR:
#   a       -> mesh (Rhino'da gorunur)
#   durum   -> kayit durumu (Panel)
# =============================================================================

import Rhino.Geometry as rg
import Rhino
import os


def _v(d, x):
    return x if d is None else d


def mesh_coerce(m):
    """Giris gercek Mesh degilse (GUID / Brep) onu gercek Mesh'e cevirir."""
    if m is None:
        return None
    if isinstance(m, rg.Mesh):
        return m
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


yaz = bool(_v(globals().get("yaz"), False))
yol = _v(globals().get("dosya_yolu"),
         u"C:\\Users\\siman\\OneDrive\\Masaüstü\\lorddoga\\deneme\\guncellenmis.obj")

if "mesh_in" in dir() and mesh_in is not None:
    mesh_in = mesh_coerce(mesh_in)
a = mesh_in if ("mesh_in" in dir() and mesh_in is not None) else None
durum = "yaz toggle'ini True yapin."

if "mesh_in" in dir() and mesh_in is not None and yaz:
    V = mesh_in.Vertices
    F = mesh_in.Faces

    sat = ["# Mimari AI - guncellenmis obj"]
    for i in range(V.Count):
        p = V[i]
        sat.append("v {0:.4f} {1:.4f} {2:.4f}".format(p.X, p.Y, p.Z))
    for i in range(F.Count):
        f = F[i]
        if f.IsTriangle:
            sat.append("f {0} {1} {2}".format(f.A + 1, f.B + 1, f.C + 1))
        else:
            sat.append("f {0} {1} {2} {3}".format(f.A + 1, f.B + 1, f.C + 1, f.D + 1))

    try:
        klas = os.path.dirname(yol)
        if klas and not os.path.isdir(klas):
            os.makedirs(klas)
        with open(yol, "w") as fd:
            fd.write("\n".join(sat))
        durum = "Kaydedildi: {}\n{} vertex, {} yuz".format(yol, V.Count, F.Count)
    except Exception as e:
        durum = "Hata: " + str(e)

# =============================================================================
# FAZ 3 - GRASSHOPPER ENTEGRASYONU: segment_v2.py
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BİLEŞENİNE YAPIŞTIRILIR.
# (Rhino 7 + Grasshopper + IronPython)
#
# NE YAPAR:
#   1. Grasshopper'daki bir 3D mesh'i alır (Meshy AI vb. modeli)
#   2. Eğitilmiş PointNet++ modeliyle her yüzeyi sınıflandırır
#   3. Sonuçları renk kodlu mesh olarak döndürür
#   4. PARAMETRE ÇIKARIR: pencere sayısı/boyutu, kapı, duvar alanı,
#      kat yüksekliği, bina boyutları → Grasshopper'da slider'larla düzenle
#
# NASIL ÇALIŞIR? (köprü yaklaşımı)
#   IronPython PyTorch çalıştıramaz. Bu yüzden:
#   1. GH → nokta bulutunu (xyz + normal) geçici dosyaya yaz
#   2. conda ortamındaki Python'u subprocess ile çağır
#   3. Python modeli çalıştırır, tahminleri yazar
#   4. GH sonucu okur, mesh'i renklendirir, parametreleri ölçer
#
# GRASSHOPPER BİLEŞENİ:
#   GİRİŞ:
#     mesh_giris  → Mesh (Params → Geometry → Mesh)
#     calistir    → Boolean Toggle (True = analiz)
#   ÇIKIŞ:
#     a           → renkli mesh (otomatik viewport önizleme)
#     rapor       → metin raporu (Panel)
#     parametreler→ ölçülen değerler (Panel)
#
# GEREKSİNİMLER:
#   - first/data/processed/model_best.pth mevcut olmalı
#   - conda ortamı "mimari_ai" kurulu (1_KURULUM.bat)
# =============================================================================

import rhinoscriptsyntax as rs
import Rhino.Geometry as rg
import Rhino
import os
import json
import math
import subprocess
import tempfile
import random

# =============================================================================
# AYARLAR
# =============================================================================

# Proje klasörünü otomatik bul (first)
def _proje_bul():
    up = os.environ.get("USERPROFILE", "C:\\Users\\User")
    adaylar = [
        os.path.join(up, "OneDrive", "Masaustu", "first"),
        os.path.join(up, "OneDrive", "Masaüstü", "first"),
        os.path.join(up, "OneDrive", "Desktop",  "first"),
        os.path.join(up, "Desktop",              "first"),
        os.path.join(up, "Masaüstü",             "first"),
    ]
    for y in adaylar:
        if os.path.isdir(y):
            return y
    return os.path.join(up, "OneDrive", "Masaüstü", "first")

PROJE_KLASORU = _proje_bul()
MODEL_YOLU = os.path.join(PROJE_KLASORU, "data", "processed", "model_best.pth")
CONDA_ENV  = "mimari_ai"
NOKTA_SAYISI = 2048   # Eğitimle aynı (model 2048 nokta bekler)

# Sınıf renkleri (0-255 RGB)
SINIF_RENKLERI = {
    0: (180, 180, 180),   # wall    → gri
    1: (160, 120,  80),   # floor   → kahve
    2: (180, 220, 255),   # ceiling → açık mavi
    3: ( 80,  50,  20),   # door    → koyu kahve
    4: ( 60, 140, 220),   # window  → mavi
    5: (200,  60,  60),   # roof    → kırmızı
    6: (200, 130,  50),   # eave    → turuncu
}
SINIF_ADLARI = {0:"Duvar", 1:"Doseme", 2:"Tavan", 3:"Kapi", 4:"Pencere", 5:"Cati", 6:"Sacak"}

# =============================================================================
# ADIM 1: MESH → NOKTA BULUTU (xyz + normal)
# =============================================================================

def mesh_to_nokta_bulutu(mesh, n_nokta):
    """
    Rhino Mesh'ten alan ağırlıklı nokta bulutu üretir.
    Her noktaya ait olduğu yüzeyin normalini de ekler (model 6 kanal bekler).

    Döndürür:
        noktalar:  [[x,y,z,nx,ny,nz], ...]
        yuzey_idx: [int, ...]  → her noktanın hangi yüzeyden geldiği
    """
    yuzey_sayisi = mesh.Faces.Count
    v = mesh.Vertices

    # Her yüzeyin alanı + normali
    alanlar  = []
    normaller = []
    for i in range(yuzey_sayisi):
        f = mesh.Faces[i]
        p0 = rg.Point3d(v[f.A].X, v[f.A].Y, v[f.A].Z)
        p1 = rg.Point3d(v[f.B].X, v[f.B].Y, v[f.B].Z)
        p2 = rg.Point3d(v[f.C].X, v[f.C].Y, v[f.C].Z)
        v1 = p1 - p0
        v2 = p2 - p0
        capraz = rg.Vector3d.CrossProduct(v1, v2)
        alan = 0.5 * capraz.Length
        if not f.IsTriangle:
            p3 = rg.Point3d(v[f.D].X, v[f.D].Y, v[f.D].Z)
            v3 = p3 - p0
            capraz2 = rg.Vector3d.CrossProduct(v2, v3)
            alan += 0.5 * capraz2.Length
        n = rg.Vector3d(capraz)
        if n.Length > 0:
            n.Unitize()
            normaller.append((n.X, n.Y, n.Z))
        else:
            normaller.append((0.0, 0.0, 1.0))
        alanlar.append(max(alan, 1e-10))

    toplam = sum(alanlar)
    olasiliklar = [a / toplam for a in alanlar]

    # Her yüzeyden alınacak nokta sayısı
    nokta_sayilari = [0] * yuzey_sayisi
    for _ in range(n_nokta):
        r = random.random()
        kum = 0.0
        for i, p in enumerate(olasiliklar):
            kum += p
            if r <= kum:
                nokta_sayilari[i] += 1
                break

    noktalar  = []
    yuzey_idx = []
    rng = random.Random(42)

    for yi in range(yuzey_sayisi):
        n = nokta_sayilari[yi]
        if n == 0:
            continue
        f = mesh.Faces[yi]
        p0 = (v[f.A].X, v[f.A].Y, v[f.A].Z)
        p1 = (v[f.B].X, v[f.B].Y, v[f.B].Z)
        p2 = (v[f.C].X, v[f.C].Y, v[f.C].Z)
        nx, ny, nz = normaller[yi]
        for _ in range(n):
            r1 = rng.random()
            r2 = rng.random()
            if r1 + r2 > 1.0:
                r1 = 1.0 - r1
                r2 = 1.0 - r2
            r3 = 1.0 - r1 - r2
            x = r1*p0[0] + r2*p1[0] + r3*p2[0]
            y = r1*p0[1] + r2*p1[1] + r3*p2[1]
            z = r1*p0[2] + r2*p1[2] + r3*p2[2]
            noktalar.append([x, y, z, nx, ny, nz])
            yuzey_idx.append(yi)

    return noktalar, yuzey_idx


def normalize_xyz(noktalar):
    """
    Sadece xyz'yi birim küreye normalize eder (eğitimle aynı).
    Normaller (3:6) değişmez.
    """
    n = len(noktalar)
    cx = sum(p[0] for p in noktalar) / n
    cy = sum(p[1] for p in noktalar) / n
    cz = sum(p[2] for p in noktalar) / n
    en_uzak = 0.0
    for p in noktalar:
        d = math.sqrt((p[0]-cx)**2 + (p[1]-cy)**2 + (p[2]-cz)**2)
        if d > en_uzak:
            en_uzak = d
    if en_uzak <= 0:
        en_uzak = 1.0
    cikti = []
    for p in noktalar:
        cikti.append([
            (p[0]-cx)/en_uzak, (p[1]-cy)/en_uzak, (p[2]-cz)/en_uzak,
            p[3], p[4], p[5]
        ])
    return cikti

# =============================================================================
# ADIM 2: PYTHON KÖPRÜ SCRIPTİ (conda'da çalışır, torch + numpy var)
# =============================================================================

KOPRU_SCRIPT = '''
import sys, json, os
import numpy as np
import torch

giris_yolu = sys.argv[1]
cikis_yolu = sys.argv[2]
model_yolu = sys.argv[3]
proje      = sys.argv[4]

sys.path.insert(0, proje)
from faz2_egitim.o3_pointnet2_model import PointNet2Segmentasyon

with open(giris_yolu, "r") as f:
    veri = json.load(f)
noktalar = np.array(veri["noktalar"], dtype=np.float32)   # [N, 6]

xyz_normal = torch.from_numpy(noktalar).unsqueeze(0)       # [1, N, 6]

cihaz = torch.device("cpu")
model = PointNet2Segmentasyon(n_sinif=7)
model.load_state_dict(torch.load(model_yolu, map_location=cihaz))
model.eval()

with torch.no_grad():
    cikis = model(xyz_normal)                              # [1, N, 7]
    tahmin = cikis[0].argmax(dim=-1).numpy().tolist()

with open(cikis_yolu, "w") as f:
    json.dump({"tahminler": tahmin}, f)

print("OK")
'''

# =============================================================================
# ADIM 3: ANALİZ (segmentasyon)
# =============================================================================

def conda_bul():
    for yol in [
        os.path.join(os.environ.get("USERPROFILE",""), "anaconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("USERPROFILE",""), "miniconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""), "anaconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""), "miniconda3", "Scripts", "conda.exe"),
        "C:\\anaconda3\\Scripts\\conda.exe",
        "C:\\miniconda3\\Scripts\\conda.exe",
        "C:\\ProgramData\\anaconda3\\Scripts\\conda.exe",
        "C:\\ProgramData\\miniconda3\\Scripts\\conda.exe",
    ]:
        if os.path.exists(yol):
            return yol
    return None


def analiz_et(mesh):
    """
    Mesh'i segmentler. Döndürür: (yuzey_siniflar, hata_mesaji)
    """
    if mesh is None or mesh.Faces.Count == 0:
        return None, "Hata: Gecerli bir mesh baglayin."

    yuzey_sayisi = mesh.Faces.Count
    gecici = tempfile.gettempdir()
    giris_json = os.path.join(gecici, "mimari_giris.json")
    cikis_json = os.path.join(gecici, "mimari_cikis.json")
    kopru_py   = os.path.join(gecici, "mimari_kopru.py")

    noktalar, yuzey_idx = mesh_to_nokta_bulutu(mesh, NOKTA_SAYISI)
    if len(noktalar) == 0:
        return None, "Hata: Mesh'ten nokta uretilemedi."

    noktalar = normalize_xyz(noktalar)

    with open(giris_json, "w") as f:
        json.dump({"noktalar": noktalar}, f)
    with open(kopru_py, "w") as f:
        f.write(KOPRU_SCRIPT)

    conda = conda_bul()
    if conda is None:
        return None, "Hata: Conda bulunamadi. 1_KURULUM.bat calistirildi mi?"
    if not os.path.exists(MODEL_YOLU):
        return None, "Hata: model_best.pth bulunamadi:\n" + MODEL_YOLU

    komut = [
        conda, "run", "-n", CONDA_ENV,
        "python", kopru_py,
        giris_json, cikis_json, MODEL_YOLU, PROJE_KLASORU
    ]
    # GhPython = IronPython 2.7 → subprocess.run / TimeoutExpired YOK.
    # Bu yuzden Popen + communicate() ile 2.7 uyumlu calistiriyoruz.
    try:
        proc = subprocess.Popen(
            komut,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False
        )
        cikti, hata_cikti = proc.communicate()
        if proc.returncode != 0:
            mesaj = hata_cikti if hata_cikti else cikti
            try:
                mesaj = mesaj.decode("utf-8", "ignore")
            except:
                mesaj = str(mesaj)
            return None, "Model hatasi:\n" + mesaj[:600]
    except Exception as e:
        return None, "Hata (subprocess): " + str(e)

    if not os.path.exists(cikis_json):
        return None, "Hata: Model cikti uretmedi (cikis_json yok)."

    with open(cikis_json, "r") as f:
        nokta_tahminleri = json.load(f)["tahminler"]

    # Nokta → yüzey oyçokluğu
    yuzey_oy = [[0]*7 for _ in range(yuzey_sayisi)]
    for no, yi in enumerate(yuzey_idx):
        if no < len(nokta_tahminleri):
            s = nokta_tahminleri[no]
            if 0 <= s < 7:
                yuzey_oy[yi][s] += 1

    yuzey_siniflar = []
    for yi in range(yuzey_sayisi):
        oy = yuzey_oy[yi]
        yuzey_siniflar.append(oy.index(max(oy)) if sum(oy) > 0 else 0)

    return yuzey_siniflar, None

# =============================================================================
# ADIM 4: PARAMETRE ÇIKARMA
# =============================================================================

def yuzey_merkez_alan(mesh, yi):
    """Bir yüzeyin merkez noktasını ve alanını döndürür."""
    v = mesh.Vertices
    f = mesh.Faces[yi]
    pts = [rg.Point3d(v[f.A].X, v[f.A].Y, v[f.A].Z),
           rg.Point3d(v[f.B].X, v[f.B].Y, v[f.B].Z),
           rg.Point3d(v[f.C].X, v[f.C].Y, v[f.C].Z)]
    if not f.IsTriangle:
        pts.append(rg.Point3d(v[f.D].X, v[f.D].Y, v[f.D].Z))
    cx = sum(p.X for p in pts) / len(pts)
    cy = sum(p.Y for p in pts) / len(pts)
    cz = sum(p.Z for p in pts) / len(pts)
    # alan (üçgen + varsa ikinci üçgen)
    v1 = pts[1] - pts[0]
    v2 = pts[2] - pts[0]
    alan = 0.5 * rg.Vector3d.CrossProduct(v1, v2).Length
    if len(pts) == 4:
        v3 = pts[3] - pts[0]
        alan += 0.5 * rg.Vector3d.CrossProduct(v2, v3).Length
    return rg.Point3d(cx, cy, cz), alan


def kumelele(merkezler, esik):
    """
    Merkez noktalarını mesafeye göre kümeler (basit birleştirme).
    Yakın yüzeyler aynı pencereye/kapıya ait kabul edilir.
    Döndürür: küme listesi (her küme = indeks listesi)
    """
    n = len(merkezler)
    atanan = [-1] * n
    kumeler = []
    for i in range(n):
        if atanan[i] != -1:
            continue
        kume = [i]
        atanan[i] = len(kumeler)
        # genişleyen arama
        deg = True
        while deg:
            deg = False
            for j in range(n):
                if atanan[j] != -1:
                    continue
                for ki in kume:
                    if merkezler[ki].DistanceTo(merkezler[j]) < esik:
                        kume.append(j)
                        atanan[j] = len(kumeler)
                        deg = True
                        break
        kumeler.append(kume)
    return kumeler


def cephe_ve_konum(cx, cy, cz, yuk, xmin, xmax, ymin, ymax, zmin):
    """
    Bir açıklığın (pencere/kapı) merkez konumundan:
      - hangi cephede olduğunu (on/arka/sol/sag)
      - cephe başından uzaklığını (u)
      - alt kenarının yerden yüksekliğini (v_alt)
    hesaplar. parametrik_kur.py açıklığı buraya yerleştirir.
    """
    d_on   = cy - ymin     # y=min cephesi
    d_arka = ymax - cy     # y=max cephesi
    d_sol  = cx - xmin     # x=min cephesi
    d_sag  = xmax - cx     # x=max cephesi
    en_yakin = min(d_on, d_arka, d_sol, d_sag)

    if en_yakin == d_on:
        cephe, u = "on", cx - xmin
    elif en_yakin == d_arka:
        cephe, u = "arka", cx - xmin
    elif en_yakin == d_sol:
        cephe, u = "sol", cy - ymin
    else:
        cephe, u = "sag", cy - ymin

    v_alt = (cz - yuk / 2.0) - zmin   # alt kenar yüksekliği
    return cephe, max(0.0, u), max(0.0, v_alt)


def parametre_cikar(mesh, yuzey_siniflar):
    """
    Segmentlenmiş mesh'ten mimari parametreleri ölçer.
    Döndürür: (parametre_dict, rapor_metni, recon_dict)
      recon_dict → parametrik_kur.py'nin okuyacağı yeniden-kurma verisi (JSON'a uygun)
    """
    v = mesh.Vertices
    # Bina sınırları
    xs = [v[i].X for i in range(v.Count)]
    ys = [v[i].Y for i in range(v.Count)]
    zs = [v[i].Z for i in range(v.Count)]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    zmin, zmax = min(zs), max(zs)
    genislik   = xmax - xmin
    derinlik   = ymax - ymin
    yukseklik  = zmax - zmin

    # Sınıf bazlı yüzeyleri topla
    sinif_yuzeyler = {s: [] for s in range(7)}
    sinif_alan     = {s: 0.0 for s in range(7)}
    for yi, s in enumerate(yuzey_siniflar):
        merkez, alan = yuzey_merkez_alan(mesh, yi)
        sinif_yuzeyler[s].append((yi, merkez, alan))
        sinif_alan[s] += alan

    # Kat sayısı tahmini (yükseklik / tipik kat 3m)
    kat_sayisi = max(1, int(round(yukseklik / 3.0)))

    # Pencere kümeleme (sınıf 4)
    pen_merkezler = [m for (yi, m, a) in sinif_yuzeyler[4]]
    esik = max(0.5, min(genislik, derinlik) * 0.15)
    pen_kumeler = kumelele(pen_merkezler, esik) if pen_merkezler else []

    pencere_listesi = []
    for kume in pen_kumeler:
        pts = [pen_merkezler[i] for i in kume]
        kx = [p.X for p in pts]; ky = [p.Y for p in pts]; kz = [p.Z for p in pts]
        gen = max(max(kx)-min(kx), max(ky)-min(ky))
        yuk = max(kz) - min(kz)
        pencere_listesi.append({
            "merkez": [round(sum(kx)/len(kx),2), round(sum(ky)/len(ky),2), round(sum(kz)/len(kz),2)],
            "genislik": round(max(gen, 0.1), 2),
            "yukseklik": round(max(yuk, 0.1), 2)
        })

    # Kapı kümeleme (sınıf 3)
    kapi_merkezler = [m for (yi, m, a) in sinif_yuzeyler[3]]
    kapi_kumeler = kumelele(kapi_merkezler, esik) if kapi_merkezler else []
    kapi_listesi = []
    for kume in kapi_kumeler:
        pts = [kapi_merkezler[i] for i in kume]
        kx = [p.X for p in pts]; ky = [p.Y for p in pts]; kz = [p.Z for p in pts]
        gen = max(max(kx)-min(kx), max(ky)-min(ky))
        yuk = max(kz) - min(kz)
        kapi_listesi.append({
            "merkez": [round(sum(kx)/len(kx),2), round(sum(ky)/len(ky),2), round(sum(kz)/len(kz),2)],
            "genislik": round(max(gen, 0.1), 2),
            "yukseklik": round(max(yuk, 0.1), 2)
        })

    duvar_alani  = sinif_alan[0]
    doseme_alani = sinif_alan[1]
    pencere_alani = sinif_alan[4]
    pen_duvar_orani = (pencere_alani / duvar_alani) if duvar_alani > 0 else 0.0

    # Çatı tipi (çatı yüzey normallerinin z bileşeni → düz mü eğimli mi)
    cati_tipi = "yok"
    cati_yuksekligi = 0.0
    if sinif_yuzeyler[5]:
        egimli = 0
        cati_zler = []
        for (yi, m, a) in sinif_yuzeyler[5]:
            cati_zler.append(m.Z)
            f = mesh.Faces[yi]
            p0 = rg.Point3d(v[f.A].X, v[f.A].Y, v[f.A].Z)
            p1 = rg.Point3d(v[f.B].X, v[f.B].Y, v[f.B].Z)
            p2 = rg.Point3d(v[f.C].X, v[f.C].Y, v[f.C].Z)
            n = rg.Vector3d.CrossProduct(p1-p0, p2-p0)
            if n.Length > 0:
                n.Unitize()
                if abs(n.Z) < 0.9:   # yataydan saparsa eğimli
                    egimli += 1
        egimli_mi = egimli > len(sinif_yuzeyler[5]) * 0.3
        cati_tipi = "egimli (besik/kirma)" if egimli_mi else "duz"
        # Çatı yüksekliği = çatı bölgesinin z aralığı (eğimliyse)
        if egimli_mi and cati_zler:
            cati_yuksekligi = max(0.0, max(cati_zler) - min(cati_zler))

    # Duvar yüksekliği = toplam - çatı; kat yüksekliği buradan
    duvar_toplam_yuk = max(2.0, yukseklik - cati_yuksekligi)
    kat_yuk = duvar_toplam_yuk / kat_sayisi

    # --- Yeniden-kurma verisi (parametrik_kur.py için) ---
    # Her açıklığın cephesi + cephe üzerindeki konumu + alt yüksekliği
    acikliklar = []
    for p in pencere_listesi:
        if p["genislik"] < 0.35 or p["yukseklik"] < 0.35:
            continue   # gürültü (0.1x0.1 gibi) — atla
        cx, cy, cz = p["merkez"]
        cephe, u, v_alt = cephe_ve_konum(cx, cy, cz, p["yukseklik"],
                                         xmin, xmax, ymin, ymax, zmin)
        acikliklar.append({
            "tip": "pencere", "cephe": cephe,
            "u": round(u, 2), "v_alt": round(v_alt, 2),
            "genislik": p["genislik"], "yukseklik": p["yukseklik"]
        })
    for k in kapi_listesi:
        if k["genislik"] < 0.35 or k["yukseklik"] < 0.5:
            continue
        cx, cy, cz = k["merkez"]
        cephe, u, v_alt = cephe_ve_konum(cx, cy, cz, k["yukseklik"],
                                         xmin, xmax, ymin, ymax, zmin)
        acikliklar.append({
            "tip": "kapi", "cephe": cephe,
            "u": round(u, 2), "v_alt": 0.0,   # kapı zeminden başlar
            "genislik": k["genislik"], "yukseklik": k["yukseklik"]
        })

    recon = {
        "genislik":       round(genislik, 2),
        "derinlik":       round(derinlik, 2),
        "kat_sayisi":     kat_sayisi,
        "kat_yuksekligi": round(kat_yuk, 2),
        "cati_yukseklik": round(cati_yuksekligi, 2),
        "acikliklar":     acikliklar,
    }

    params = {
        "bina_genislik":   round(genislik, 2),
        "bina_derinlik":   round(derinlik, 2),
        "bina_yukseklik":  round(yukseklik, 2),
        "kat_sayisi":      kat_sayisi,
        "kat_yuksekligi":  round(yukseklik / kat_sayisi, 2),
        "pencere_sayisi":  len(pencere_listesi),
        "kapi_sayisi":     len(kapi_listesi),
        "duvar_alani_m2":  round(duvar_alani, 2),
        "doseme_alani_m2": round(doseme_alani, 2),
        "pencere_duvar_orani": round(pen_duvar_orani, 3),
        "cati_tipi":       cati_tipi,
        "pencereler":      pencere_listesi,
        "kapilar":         kapi_listesi,
    }

    # Rapor metni
    sat = ["=== CIKARILAN PARAMETRELER ==="]
    sat.append("Bina: {} x {} x {} m".format(
        params["bina_genislik"], params["bina_derinlik"], params["bina_yukseklik"]))
    sat.append("Kat sayisi: {} (~{} m/kat)".format(params["kat_sayisi"], params["kat_yuksekligi"]))
    sat.append("Cati tipi: {}".format(params["cati_tipi"]))
    sat.append("")
    sat.append("Pencere sayisi: {}".format(params["pencere_sayisi"]))
    for i, p in enumerate(pencere_listesi):
        sat.append("  P{}: {} x {} m  @ {}".format(i+1, p["genislik"], p["yukseklik"], p["merkez"]))
    sat.append("Kapi sayisi: {}".format(params["kapi_sayisi"]))
    for i, k in enumerate(kapi_listesi):
        sat.append("  K{}: {} x {} m  @ {}".format(i+1, k["genislik"], k["yukseklik"], k["merkez"]))
    sat.append("")
    sat.append("Duvar alani:  {} m2".format(params["duvar_alani_m2"]))
    sat.append("Doseme alani: {} m2".format(params["doseme_alani_m2"]))
    sat.append("Pencere/duvar orani: %{}".format(round(pen_duvar_orani*100, 1)))

    return params, "\n".join(sat), recon

# =============================================================================
# ADIM 5: MESH RENKLENDİR
# =============================================================================

def mesh_renklendir(mesh, yuzey_siniflar):
    import System.Drawing as sd
    renkli = mesh.DuplicateMesh()
    renkli.VertexColors.CreateMonotoneMesh(sd.Color.White)
    for yi in range(renkli.Faces.Count):
        if yi >= len(yuzey_siniflar):
            continue
        r, g, b = SINIF_RENKLERI.get(yuzey_siniflar[yi], (200, 200, 200))
        renk = sd.Color.FromArgb(255, r, g, b)
        f = renkli.Faces[yi]
        renkli.VertexColors[f.A] = renk
        renkli.VertexColors[f.B] = renk
        renkli.VertexColors[f.C] = renk
        if not f.IsTriangle:
            renkli.VertexColors[f.D] = renk
    return renkli

# =============================================================================
# GRASSHOPPER ÇALIŞMA NOKTASI
# =============================================================================
# Giriş:  mesh_giris (Mesh), calistir (bool)
# Çıkış:  a (renkli mesh), rapor (metin), parametreler (JSON metin)

def _geo_to_mesh(g):
    """Mesh/Brep/Extrusion/SubD geometrisini birlesik Mesh'e cevirir."""
    if g is None:
        return None
    if isinstance(g, rg.Mesh):
        return g
    # Brep'e cevirebileceklerimiz (Extrusion, SubD vb.)
    brep = None
    if isinstance(g, rg.Brep):
        brep = g
    else:
        for cevir in ("ToBrep", "ToBrep"):
            try:
                brep = g.ToBrep()
                break
            except:
                brep = None
    if brep is not None:
        birlesik = rg.Mesh()
        parcalar = rg.Mesh.CreateFromBrep(brep, rg.MeshingParameters.Default)
        if parcalar:
            for ms in parcalar:
                birlesik.Append(ms)
        if birlesik.Faces.Count > 0:
            return birlesik
    return None


def mesh_coerce(m):
    """
    Giriş gerçek bir Mesh degilse (Rhino'dan GUID referansi ya da Brep
    geldiyse) onu gercek Rhino.Geometry.Mesh'e cevirir.
    Type hint ayarlanmasa bile calismayi garantiler.
    """
    if m is None:
        return None
    if isinstance(m, rg.Mesh):
        return m
    # Dogrudan geometri (Brep/Extrusion) geldiyse
    g = _geo_to_mesh(m)
    if g is not None:
        return g
    # GUID geldiyse Rhino dokumanindan geometriyi getir
    try:
        import System
        if isinstance(m, System.Guid):
            doc = Rhino.RhinoDoc.ActiveDoc
            obj = None
            try:
                obj = doc.Objects.FindId(m)
            except:
                try:
                    obj = doc.Objects.Find(m)
                except:
                    obj = None
            if obj is not None:
                g2 = _geo_to_mesh(obj.Geometry)
                if g2 is not None:
                    return g2
    except:
        pass
    return m

a              = None
rapor          = "Mesh baglayin ve 'calistir' toggle'ini True yapin."
parametreler   = ""
parametre_json = ""    # parametrik_kur.py'ye giden makine-okur veri
siniflar       = None  # pencere_editle.py (Program 2) icin yuzey etiketleri

if "calistir" in dir() and calistir and "mesh_giris" in dir() and mesh_giris is not None:
    mesh_giris = mesh_coerce(mesh_giris)
    siniflar, hata = analiz_et(mesh_giris)
    if hata:
        rapor = hata
        a = mesh_giris
    else:
        a = mesh_renklendir(mesh_giris, siniflar)
        from collections import Counter as _C
        sayac = _C(siniflar)
        sat = ["=== SEGMENTASYON ==="]
        sat.append("Toplam yuzey: {}".format(len(siniflar)))
        for s in range(7):
            sat.append("  {}: {} yuzey".format(SINIF_ADLARI[s], sayac.get(s, 0)))
        rapor = "\n".join(sat)

        params, param_rapor, recon = parametre_cikar(mesh_giris, siniflar)
        parametreler   = param_rapor
        parametre_json = json.dumps(recon)   # → parametrik_kur'a bagla
        print(rapor)
        print()
        print(param_rapor)

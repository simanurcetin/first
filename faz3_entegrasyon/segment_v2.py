# =============================================================================
# FAZ 3 - GRASSHOPPER ENTEGRASYONU: segment_v2.py
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BİLEŞENİNE YAPIŞTIRILIR.
# (Rhino 7 + Grasshopper + IronPython)
#
# NE YAPAR:
#   Grasshopper'daki bir 3D mesh'i alır.
#   Eğitilmiş modeli (model.pth) kullanarak her yüzeyi sınıflandırır.
#   Sonuçları renk kodlu olarak Grasshopper'a geri döndürür.
#   Slider değiştiğinde otomatik güncellenir.
#
# NASIL ÇALIŞIR?
#   IronPython PyTorch'u çalıştıramaz.
#   Bu yüzden "köprü" yaklaşımı kullanılır:
#   1. Grasshopper → nokta bulutunu geçici bir .npy dosyasına yaz
#   2. Conda ortamındaki Python'u subprocess ile çağır
#   3. Python modeli çalıştırır, sonucu başka bir .npy dosyasına yazar
#   4. Grasshopper sonucu okur ve mesh'i renklendirir
#
# GRASSHOPPER BİLEŞENİ BAĞLANTILARI:
#   Giriş:
#     mesh_giris  → Mesh bileşenine bağlayın (Params → Geometry → Mesh)
#     calistir    → Boolean Toggle (True yaptığınızda analiz başlar)
#   Çıkış:
#     renkli_mesh → Renk kodlu mesh (Mesh Preview bileşenine bağlayın)
#     rapor       → Metin raporu (Panel bileşenine bağlayın)
#
# KURULUM GEREKSİNİMLERİ:
#   - lorddoga/data/processed/model_best.pth → mevcut olmalı
#   - conda ortamı "mimari_ai" kurulu olmalı
#   - 1_KURULUM.bat çalıştırılmış olmalı
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

# Proje klasörü (kendi yolunuzu buraya yazın)
PROJE_KLASORU = os.path.join(
    os.environ.get("USERPROFILE", "C:\\Users\\User"),
    "Desktop", "lorddoga"
)

MODEL_YOLU = os.path.join(PROJE_KLASORU, "data", "processed", "model_best.pth")

# Conda ortamı adı
CONDA_ENV = "mimari_ai"

# Her analiz için kaç nokta örneklenecek
NOKTA_SAYISI = 1024

# Sınıf renkleri (Grasshopper için 0-255 RGB)
SINIF_RENKLERI = {
    0: (200, 200, 200),   # wall    → gri
    1: (180, 140, 100),   # floor   → kahve
    2: (240, 240, 240),   # ceiling → beyaza yakın
    3: (120,  80,  40),   # door    → koyu kahve
    4: ( 80, 160, 220),   # window  → mavi
    5: (160,  60,  60),   # roof    → kırmızı
    6: (140,  90,  50),   # eave    → turuncu-kahve
}

SINIF_ADLARI = {0:"Duvar", 1:"Döşeme", 2:"Tavan", 3:"Kapı", 4:"Pencere", 5:"Çatı", 6:"Saçak"}

# =============================================================================
# ADIM 1: MESH'TEN NOKTA BULUTU ÜRET (IronPython ile)
# =============================================================================

def mesh_to_nokta_bulutu(mesh, n_nokta):
    """
    Rhino Mesh nesnesinden alan ağırlıklı nokta bulutu üretir.

    Her yüzey için:
    - Alanına göre orantılı nokta sayısı alır
    - Yüzey içine rastgele noktalar serper

    Döndürür:
        noktalar: [[x,y,z], ...]  → n_nokta adet koordinat
        yuzey_idx: [int, ...]     → her noktanın hangi yüzeyden geldiği
    """
    yuzey_sayisi = mesh.Faces.Count

    # Her yüzeyin alanını hesapla
    alanlar = []
    for i in range(yuzey_sayisi):
        f = mesh.Faces[i]
        # Yüzeyi üçgene(lere) böl
        v = mesh.Vertices
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
        alanlar.append(max(alan, 1e-10))

    toplam_alan = sum(alanlar)
    olasiliklar = [a / toplam_alan for a in alanlar]

    # Her yüzeyden alınacak nokta sayısı
    nokta_sayilari = [0] * yuzey_sayisi
    for _ in range(n_nokta):
        r = random.random()
        kumulatif = 0.0
        for i, p in enumerate(olasiliklar):
            kumulatif += p
            if r <= kumulatif:
                nokta_sayilari[i] += 1
                break

    # Noktaları üret
    noktalar = []
    yuzey_idx = []

    rng = random.Random(42)

    for yuz_i in range(yuzey_sayisi):
        n = nokta_sayilari[yuz_i]
        if n == 0:
            continue

        f = mesh.Faces[yuz_i]
        v = mesh.Vertices
        p0 = (v[f.A].X, v[f.A].Y, v[f.A].Z)
        p1 = (v[f.B].X, v[f.B].Y, v[f.B].Z)
        p2 = (v[f.C].X, v[f.C].Y, v[f.C].Z)

        for _ in range(n):
            r1 = rng.random()
            r2 = rng.random()
            if r1 + r2 > 1.0:
                r1 = 1.0 - r1
                r2 = 1.0 - r2
            r3 = 1.0 - r1 - r2
            x = r1 * p0[0] + r2 * p1[0] + r3 * p2[0]
            y = r1 * p0[1] + r2 * p1[1] + r3 * p2[1]
            z = r1 * p0[2] + r2 * p1[2] + r3 * p2[2]
            noktalar.append([x, y, z])
            yuzey_idx.append(yuz_i)

    return noktalar, yuzey_idx


def normalize(noktalar):
    """Nokta bulutunu [-1,1] aralığına normalize eder."""
    xs = [p[0] for p in noktalar]
    ys = [p[1] for p in noktalar]
    zs = [p[2] for p in noktalar]
    cx, cy, cz = sum(xs)/len(xs), sum(ys)/len(ys), sum(zs)/len(zs)
    merkez_noktalar = [[p[0]-cx, p[1]-cy, p[2]-cz] for p in noktalar]
    en_uzak = max(math.sqrt(p[0]**2+p[1]**2+p[2]**2) for p in merkez_noktalar)
    if en_uzak > 0:
        return [[p[0]/en_uzak, p[1]/en_uzak, p[2]/en_uzak] for p in merkez_noktalar]
    return merkez_noktalar

# =============================================================================
# ADIM 2: PYTHON KÖPRÜ SCRIPTİ (Conda'da çalışacak)
# =============================================================================

KOPRU_SCRIPT = """
# Bu script conda run ile çalıştırılır
# Nokta bulutunu okur, modeli çalıştırır, tahminleri yazar
import sys, json, os
import numpy as np
import torch

giris_yolu = sys.argv[1]   # nokta bulutu dosyası
cikis_yolu = sys.argv[2]   # tahmin çıktısı
model_yolu = sys.argv[3]   # model.pth

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in dir() else os.getcwd())

# Model mimarisini import et
try:
    from faz2_egitim.o3_pointnet2_model import PointNet2Segmentasyon
except:
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(
        "model",
        os.path.join(os.path.dirname(model_yolu), "..", "..", "faz2_egitim", "03_pointnet2_model.py")
    )
    mod = importlib.util.load_from_spec(spec)
    spec.loader.exec_module(mod)
    PointNet2Segmentasyon = mod.PointNet2Segmentasyon

# Nokta bulutunu oku
with open(giris_yolu, "r") as f:
    veri = json.load(f)
noktalar = np.array(veri["noktalar"], dtype=np.float32)  # [N, 3]

# Tensöre çevir
xyz = torch.from_numpy(noktalar).unsqueeze(0)  # [1, N, 3]

# Modeli yükle
cihaz = torch.device("cpu")
model = PointNet2Segmentasyon(n_sinif=7)
model.load_state_dict(torch.load(model_yolu, map_location=cihaz))
model.eval()

# Tahmin
with torch.no_grad():
    cikis = model(xyz)
    tahmin = cikis[0].argmax(dim=-1).numpy().tolist()

# Kaydet
with open(cikis_yolu, "w") as f:
    json.dump({"tahminler": tahmin}, f)

print("OK")
"""

# =============================================================================
# ADIM 3: ANALİZ FONKSİYONU
# =============================================================================

def analiz_et(mesh):
    """
    Mesh'i analiz eder, her yüzey için sınıf tahmini döndürür.

    Döndürür:
        yuzey_siniflar: [int] → her yüzeyin tahmini sınıfı
        rapor_metni:    str   → özet rapor
    """
    if mesh is None or mesh.Faces.Count == 0:
        return None, "Hata: Geçerli bir mesh bağlayın."

    yuzey_sayisi = mesh.Faces.Count

    # Geçici dosya yolları
    gecici_klasor = tempfile.gettempdir()
    giris_json  = os.path.join(gecici_klasor, "mimari_giris.json")
    cikis_json  = os.path.join(gecici_klasor, "mimari_cikis.json")
    kopru_py    = os.path.join(gecici_klasor, "mimari_kopru.py")

    # 1. Nokta bulutu üret
    noktalar, yuzey_idx = mesh_to_nokta_bulutu(mesh, NOKTA_SAYISI)
    if len(noktalar) == 0:
        return None, "Hata: Mesh'ten nokta üretilemedi."

    noktalar = normalize(noktalar)

    # 2. Giriş JSON'unu yaz
    with open(giris_json, "w") as f:
        json.dump({"noktalar": noktalar}, f)

    # 3. Köprü scriptini yaz
    with open(kopru_py, "w") as f:
        f.write(KOPRU_SCRIPT)

    # 4. Conda ortamında Python'u çalıştır
    conda_komut = None
    conda_konumlari = [
        os.path.join(os.environ.get("USERPROFILE",""), "anaconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("USERPROFILE",""), "miniconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""), "anaconda3", "Scripts", "conda.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA",""), "miniconda3", "Scripts", "conda.exe"),
        "C:\\anaconda3\\Scripts\\conda.exe",
        "C:\\miniconda3\\Scripts\\conda.exe",
        "C:\\ProgramData\\anaconda3\\Scripts\\conda.exe",
        "C:\\ProgramData\\miniconda3\\Scripts\\conda.exe",
    ]
    for yol in conda_konumlari:
        if os.path.exists(yol):
            conda_komut = yol
            break

    if conda_komut is None:
        return None, "Hata: Conda bulunamadı. 1_KURULUM.bat çalıştırıldı mı?"

    if not os.path.exists(MODEL_YOLU):
        return None, "Hata: model_best.pth bulunamadı.\nFaz 2'yi tamamlayıp modeli lorddoga/data/processed/ klasörüne koyun."

    komut = [
        conda_komut, "run", "-n", CONDA_ENV,
        "python", kopru_py,
        giris_json, cikis_json, MODEL_YOLU
    ]

    try:
        sonuc = subprocess.run(
            komut,
            capture_output=True,
            text=True,
            timeout=60   # 60 saniye zaman aşımı
        )
        if sonuc.returncode != 0:
            return None, "Model hatası:\n" + sonuc.stderr[:500]
    except subprocess.TimeoutExpired:
        return None, "Hata: Model 60 saniyede yanıt vermedi."
    except Exception as e:
        return None, "Hata: " + str(e)

    # 5. Sonuçları oku
    with open(cikis_json, "r") as f:
        cikis = json.load(f)
    nokta_tahminleri = cikis["tahminler"]   # Her nokta için sınıf

    # 6. Noktalardan yüzeylere geçiş: oyçokluğu
    # Her yüzey, o yüzeyden örneklenen noktaların çoğunluk sınıfını alır
    yuzey_oy = [[0]*7 for _ in range(yuzey_sayisi)]
    for nokta_no, yuz_i in enumerate(yuzey_idx):
        if nokta_no < len(nokta_tahminleri):
            sinif = nokta_tahminleri[nokta_no]
            if 0 <= sinif < 7:
                yuzey_oy[yuz_i][sinif] += 1

    yuzey_siniflar = []
    for yuz_i in range(yuzey_sayisi):
        oylar = yuzey_oy[yuz_i]
        kazanan = oylar.index(max(oylar)) if sum(oylar) > 0 else 0
        yuzey_siniflar.append(kazanan)

    # 7. Rapor
    from collections import Counter
    sayac = Counter(yuzey_siniflar)
    rapor_satirlari = ["=== Segmentasyon Sonucu ==="]
    rapor_satirlari.append(f"Toplam yüzey: {yuzey_sayisi}")
    rapor_satirlari.append("")
    for sinif_id in range(7):
        adet = sayac.get(sinif_id, 0)
        oran = adet / yuzey_sayisi * 100 if yuzey_sayisi > 0 else 0
        rapor_satirlari.append(f"  {SINIF_ADLARI[sinif_id]}: {adet} yüzey (%{oran:.1f})")
    rapor_metni = "\n".join(rapor_satirlari)

    return yuzey_siniflar, rapor_metni


# =============================================================================
# ADIM 4: MESH'İ RENKLENDİR
# =============================================================================

def mesh_renklendir(mesh, yuzey_siniflar):
    """
    Her yüzeyi sınıf rengine göre boyar.
    Grasshopper'a gönderilebilen renkli bir mesh döndürür.
    """
    import System.Drawing as sd

    renkli_mesh = mesh.DuplicateMesh()
    renkli_mesh.VertexColors.CreateMonotoneMesh(sd.Color.White)

    # Her yüzey için rengi köşelere ata
    for yuz_i in range(renkli_mesh.Faces.Count):
        if yuz_i >= len(yuzey_siniflar):
            continue
        sinif = yuzey_siniflar[yuz_i]
        r, g, b = SINIF_RENKLERI.get(sinif, (200, 200, 200))
        renk = sd.Color.FromArgb(255, r, g, b)

        f = renkli_mesh.Faces[yuz_i]
        renkli_mesh.VertexColors[f.A] = renk
        renkli_mesh.VertexColors[f.B] = renk
        renkli_mesh.VertexColors[f.C] = renk
        if not f.IsTriangle:
            renkli_mesh.VertexColors[f.D] = renk

    return renkli_mesh


# =============================================================================
# GRASSHOPPER ÇALIŞMA NOKTASI
# =============================================================================
# Bu blok Grasshopper tarafından çalıştırılır.
# Giriş değişkenleri: mesh_giris (Mesh), calistir (bool)
# Çıkış değişkenleri: renkli_mesh, rapor

# Varsayılan çıkışlar
renkli_mesh = None
rapor = "Mesh bağlayın ve 'calistir' toggle'ını True yapın."

if calistir and mesh_giris is not None:
    rapor = "Analiz çalışıyor, lütfen bekleyin..."
    siniflar, rapor = analiz_et(mesh_giris)

    if siniflar is not None:
        renkli_mesh = mesh_renklendir(mesh_giris, siniflar)
    else:
        renkli_mesh = mesh_giris

# =============================================================================
# FAZ 2 - ADIM 1: OBJ → NOKTA BULUTU DÖNÜŞÜMÜ
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA ÇALIŞTIRILIR.
#
# NE YAPAR:
#   Faz 1'de üretilen 500 adet .obj dosyasını okur.
#   Her bina modelinden 2048 nokta örnekler.
#   Her noktaya o yüzeyin sınıf etiketini atar (wall=0, window=4 vb.)
#   Sonucu .npy formatında kaydeder (numpy dizisi).
#
# NEDEN NOKTA BULUTU?
#   PointNet++ ağı, yüzey mesh'i değil nokta bulutu alır.
#   Mesh yüzeyinin her köşesine ve içine noktalar serpiştiriyoruz.
#   Bu noktalar "3D uzaydaki koordinatlar + sınıf etiketi" içerir.
#
# ÇIKTI DOSYASI YAPISI (her .npy dosyası):
#   [N, 4] boyutlu dizi:
#   - [:, 0:3] → x, y, z koordinatları
#   - [:, 3]   → sınıf etiketi (0-6 arası tam sayı)
#
# COLAB'A YÜKLEME:
#   1. Bu dosyayı ve data/obj_files + data/json_files klasörlerini Drive'a yükle
#   2. Colab'da bu scripti çalıştır
#   3. Çıktı: data/processed/pointclouds/ klasörü
# =============================================================================

import numpy as np
import os
import json
from tqdm import tqdm   # İlerleme çubuğu

# =============================================================================
# AYARLAR
# =============================================================================

OBJ_KLASORU  = "data/obj_files"    # Faz 1 çıktısı
JSON_KLASORU = "data/json_files"   # Faz 1 çıktısı
CIKTI_KLASORU = "data/processed/pointclouds"

NOKTA_SAYISI = 2048   # Her modelden kaç nokta örneklenecek
                       # Daha fazla = daha iyi ama daha yavaş eğitim

# =============================================================================
# YARDIMCI FONKSİYONLAR
# =============================================================================

def obj_oku(dosya_yolu):
    """
    .obj dosyasını okur, köşe koordinatları ve yüzey listesini döndürür.

    OBJ formatı:
      v 1.0 2.0 3.0   → köşe koordinatı
      f 1 2 3 4       → yüzey (hangi köşeler birbirine bağlı)
                        (OBJ'de indeksler 1'den başlar!)
    """
    köseler = []   # Her köşenin [x, y, z] koordinatları
    yuzeyler = []  # Her yüzeyin köşe indeksleri listesi

    with open(dosya_yolu, "r") as f:
        for satir in f:
            satir = satir.strip()
            if satir.startswith("v "):
                # Köşe satırı: "v x y z"
                parcalar = satir.split()
                köseler.append([float(parcalar[1]),
                                 float(parcalar[2]),
                                 float(parcalar[3])])
            elif satir.startswith("f "):
                # Yüzey satırı: "f 1 2 3" veya "f 1 2 3 4"
                parcalar = satir.split()[1:]
                # OBJ indeksler 1'den başlar, Python 0'dan → 1 çıkar
                indeksler = [int(p.split("/")[0]) - 1 for p in parcalar]
                yuzeyler.append(indeksler)

    return np.array(köseler, dtype=np.float32), yuzeyler


def ucgen_alan(p0, p1, p2):
    """
    Üç nokta ile tanımlanan üçgenin alanını hesaplar.
    Vektörel çarpım yöntemi kullanılır.
    """
    v1 = p1 - p0
    v2 = p2 - p0
    capraz = np.cross(v1, v2)
    return 0.5 * np.linalg.norm(capraz)


def meshten_nokta_ornekle(köseler, yuzeyler, etiketler, n_nokta):
    """
    Mesh yüzeylerinden alan ağırlıklı olarak nokta örnekler.

    NEDEN ALAN AĞIRLIKLI?
    Büyük bir çatı yüzeyi, küçük bir kapı yüzeyinden çok daha fazla
    nokta almalıdır. Böylece her bölge orantılı temsil edilir.

    Adımlar:
    1. Her yüzeyin alanını hesapla
    2. Alanlara göre olasılık dağılımı oluştur (büyük yüzey → yüksek olasılık)
    3. Bu dağılıma göre rastgele yüzey seç
    4. Seçilen yüzeyin içine rastgele nokta koy
    5. O noktaya yüzeyin etiketini ata
    """

    # Her yüzeyi üçgenlere böl ve alanını hesapla
    ucgen_alanlari = []
    ucgen_etiketleri = []
    ucgen_kose_listeleri = []

    for yuz_idx, yuzey in enumerate(yuzeyler):
        if yuz_idx >= len(etiketler):
            continue

        etiket = etiketler[yuz_idx]

        # Dörtgen yüzey → 2 üçgene böl
        if len(yuzey) == 4:
            ucgen_ciftleri = [
                [yuzey[0], yuzey[1], yuzey[2]],
                [yuzey[0], yuzey[2], yuzey[3]]
            ]
        elif len(yuzey) == 3:
            ucgen_ciftleri = [yuzey]
        else:
            continue  # 5+ köşeli yüzey (nadir), atla

        for ucgen in ucgen_ciftleri:
            if max(ucgen) >= len(köseler):
                continue   # Bozuk indeks, atla
            p0 = köseler[ucgen[0]]
            p1 = köseler[ucgen[1]]
            p2 = köseler[ucgen[2]]
            alan = ucgen_alan(p0, p1, p2)
            ucgen_alanlari.append(alan)
            ucgen_etiketleri.append(etiket)
            ucgen_kose_listeleri.append((p0, p1, p2))

    if not ucgen_alanlari:
        # Hiç geçerli üçgen yoksa sıfır nokta bulutu döndür
        return np.zeros((n_nokta, 4), dtype=np.float32)

    # Alan ağırlıklı olasılık dağılımı
    toplam_alan = sum(ucgen_alanlari)
    olasiliklar = [a / toplam_alan for a in ucgen_alanlari]

    # n_nokta kadar üçgen seç (tekrar olabilir)
    secili_indeksler = np.random.choice(
        len(ucgen_alanlari),
        size=n_nokta,
        replace=True,
        p=olasiliklar
    )

    # Seçilen üçgenlerin içine rastgele nokta üret
    # (Barycentric koordinat yöntemi)
    noktalar = np.zeros((n_nokta, 4), dtype=np.float32)

    for i, idx in enumerate(secili_indeksler):
        p0, p1, p2 = ucgen_kose_listeleri[idx]
        etiket = ucgen_etiketleri[idx]

        # Üçgen içi rastgele nokta: barycentric yöntem
        r1 = np.random.random()
        r2 = np.random.random()
        if r1 + r2 > 1.0:
            r1 = 1.0 - r1
            r2 = 1.0 - r2
        r3 = 1.0 - r1 - r2

        x = r1 * p0[0] + r2 * p1[0] + r3 * p2[0]
        y = r1 * p0[1] + r2 * p1[1] + r3 * p2[1]
        z = r1 * p0[2] + r2 * p1[2] + r3 * p2[2]

        noktalar[i] = [x, y, z, etiket]

    return noktalar


def normalize_et(noktalar_xyzl):
    """
    Nokta bulutunu birim küreye normalize eder.

    NEDEN GEREKLİ?
    Farklı binalar farklı boyutlarda (6m-20m arası).
    PointNet++ ağı her zaman aynı ölçekte nokta bulutu beklediği için
    hepsini aynı [-1, +1] aralığına sıkıştırıyoruz.

    Sadece xyz koordinatları normalize edilir, etiket (4. sütun) değişmez.
    """
    xyz = noktalar_xyzl[:, 0:3].copy()

    # Merkezi orijine taşı
    merkez = xyz.mean(axis=0)
    xyz -= merkez

    # En uzak noktayı bul ve birim küreye sığdır
    en_uzak = np.max(np.sqrt(np.sum(xyz ** 2, axis=1)))
    if en_uzak > 0:
        xyz /= en_uzak

    noktalar_xyzl[:, 0:3] = xyz
    return noktalar_xyzl


# =============================================================================
# ANA DÖNÜŞÜM FONKSİYONU
# =============================================================================

def donustur():
    os.makedirs(CIKTI_KLASORU, exist_ok=True)

    # OBJ dosyalarını listele
    obj_dosyalari = sorted([
        f for f in os.listdir(OBJ_KLASORU) if f.endswith(".obj")
    ])

    print("=" * 60)
    print(f"  OBJ → NOKTA BULUTU DÖNÜŞÜMÜ")
    print(f"  Toplam model: {len(obj_dosyalari)}")
    print(f"  Her modelden {NOKTA_SAYISI} nokta örneklenecek")
    print("=" * 60)

    basarili = 0
    hatali = 0

    for obj_dosya in tqdm(obj_dosyalari, desc="Dönüştürülüyor"):
        model_adi = obj_dosya.replace(".obj", "")   # örn: "bina_0042"
        obj_yol   = os.path.join(OBJ_KLASORU, obj_dosya)
        json_yol  = os.path.join(JSON_KLASORU, model_adi + ".json")
        cikti_yol = os.path.join(CIKTI_KLASORU, model_adi + ".npy")

        try:
            # JSON'dan etiketleri oku
            with open(json_yol, "r", encoding="utf-8") as jf:
                bilgi = json.load(jf)
            etiketler = bilgi["etiket_listesi"]

            # OBJ'yi oku
            köseler, yuzeyler = obj_oku(obj_yol)

            # Nokta bulutu üret
            noktalar = meshten_nokta_ornekle(köseler, yuzeyler, etiketler, NOKTA_SAYISI)

            # Normalize et
            noktalar = normalize_et(noktalar)

            # Kaydet
            np.save(cikti_yol, noktalar)
            basarili += 1

        except Exception as e:
            print(f"\n  HATA - {model_adi}: {e}")
            hatali += 1

    print(f"\n  Tamamlandı: {basarili} başarılı, {hatali} hatalı")
    print(f"  Çıktı klasörü: {CIKTI_KLASORU}")

    # Özet istatistik
    if basarili > 0:
        ornek = np.load(os.path.join(CIKTI_KLASORU, obj_dosyalari[0].replace(".obj", ".npy")))
        print(f"\n  Örnek dosya boyutu: {ornek.shape}  (nokta_sayisi x 4)")
        print(f"  Sütunlar: [x, y, z, sinif_etiketi]")
        siniflar, sayilar = np.unique(ornek[:, 3].astype(int), return_counts=True)
        print(f"  İlk modelde sınıf dağılımı:")
        sinif_adlari = {0:"wall", 1:"floor", 2:"ceiling", 3:"door", 4:"window", 5:"roof", 6:"eave"}
        for s, n in zip(siniflar, sayilar):
            print(f"    {sinif_adlari.get(s, str(s))}: {n} nokta")


if __name__ == "__main__":
    donustur()

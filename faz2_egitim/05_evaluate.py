# =============================================================================
# FAZ 2 - ADIM 5: DEĞERLENDİRME VE GÖRSELLEŞTİRME
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA ÇALIŞTIRILIR (04_train.py'den sonra).
#
# NE YAPAR:
#   Eğitilmiş modeli test verisi üzerinde değerlendirir.
#   Sınıf bazlı doğruluk ve IoU (Intersection over Union) raporlar.
#   Örnek tahminleri görselleştirir (renk kodlu nokta bulutu).
#
# IoU NEDİR?
#   "Kesişim bölünmesi birleşim" — segmentasyon kalitesinin en yaygın ölçüsü.
#   Bir sınıf için: (doğru tahmin edilen) / (gerçek + tahmin edilen - ortak)
#   0.0 = hiç doğru yok, 1.0 = mükemmel
# =============================================================================

import torch
import numpy as np
import os
import matplotlib
matplotlib.use("Agg")  # Ekransız Colab için
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

from faz2_egitim.o2_dataset import loader_olustur
from faz2_egitim.o3_pointnet2_model import PointNet2Segmentasyon

# =============================================================================
# AYARLAR
# =============================================================================

MODEL_YOLU      = "data/processed/model_best.pth"
NOKTA_KLASORU   = "data/processed/pointclouds"
RAPOR_KLASORU   = "data/processed/rapor"
N_SINIF         = 7

SINIF_ADLARI = {0:"wall", 1:"floor", 2:"ceiling", 3:"door", 4:"window", 5:"roof", 6:"eave"}

# Görselleştirme renkleri (RGB 0-1 arası)
SINIF_RENKLERI = {
    0: (0.78, 0.78, 0.78),   # wall    → gri
    1: (0.70, 0.55, 0.39),   # floor   → kahve
    2: (0.94, 0.94, 0.94),   # ceiling → açık gri
    3: (0.47, 0.31, 0.16),   # door    → koyu kahve
    4: (0.31, 0.63, 0.86),   # window  → mavi
    5: (0.63, 0.24, 0.24),   # roof    → kırmızı
    6: (0.55, 0.35, 0.20),   # eave    → turuncu-kahve
}

# =============================================================================
# DEĞERLENDİRME
# =============================================================================

def iou_hesapla(tahmin, gercek, n_sinif):
    """
    Sınıf bazlı IoU (Intersection over Union) hesaplar.

    Döndürür: [n_sinif] boyutlu array, her sınıfın IoU değeri
    """
    iou_listesi = []
    for s in range(n_sinif):
        kesisim = ((tahmin == s) & (gercek == s)).sum()
        birlesim = ((tahmin == s) | (gercek == s)).sum()
        if birlesim == 0:
            iou_listesi.append(float("nan"))   # Bu sınıf hiç yok
        else:
            iou_listesi.append(kesisim / birlesim)
    return np.array(iou_listesi)


def tam_degerlendir(model, loader, cihaz):
    """
    Tüm test seti üzerinde değerlendirme yapar.

    Döndürür:
        genel_dogr:    Genel doğruluk (tüm noktalar)
        sinif_dogr:    Sınıf bazlı doğruluk [n_sinif]
        ortalama_iou:  mIoU (Mean IoU) — segmentasyonun ana metriği
        sinif_iou:     Sınıf bazlı IoU [n_sinif]
    """
    model.eval()

    tum_tahmin = []
    tum_gercek = []

    with torch.no_grad():
        for xyz, etiketler in loader:
            xyz       = xyz.to(cihaz)
            etiketler = etiketler.to(cihaz)

            cikis = model(xyz)                      # [B, N, n_sinif]
            tahmin = cikis.argmax(dim=-1)            # [B, N]

            tum_tahmin.append(tahmin.cpu().numpy())
            tum_gercek.append(etiketler.cpu().numpy())

    tum_tahmin = np.concatenate(tum_tahmin).flatten()
    tum_gercek = np.concatenate(tum_gercek).flatten()

    # Genel doğruluk
    genel_dogr = (tum_tahmin == tum_gercek).mean()

    # Sınıf bazlı doğruluk
    sinif_dogr = np.zeros(N_SINIF)
    for s in range(N_SINIF):
        maske = (tum_gercek == s)
        if maske.sum() > 0:
            sinif_dogr[s] = (tum_tahmin[maske] == s).mean()

    # IoU
    sinif_iou = iou_hesapla(tum_tahmin, tum_gercek, N_SINIF)
    gecerli_iou = sinif_iou[~np.isnan(sinif_iou)]
    ortalama_iou = gecerli_iou.mean()

    return genel_dogr, sinif_dogr, ortalama_iou, sinif_iou


# =============================================================================
# GÖRSELLEŞTİRME
# =============================================================================

def gorsellestir(model, loader, cihaz, n_ornek=3):
    """
    Birkaç test modeli için tahmin vs gerçek karşılaştırması çizer.
    """
    model.eval()
    os.makedirs(RAPOR_KLASORU, exist_ok=True)

    veri_iter = iter(loader)

    for ornek_no in range(n_ornek):
        try:
            xyz, gercek = next(veri_iter)
        except StopIteration:
            break

        # Sadece ilk modeli al
        xyz_tek    = xyz[0:1].to(cihaz)      # [1, N, 3]
        gercek_tek = gercek[0].numpy()        # [N]

        with torch.no_grad():
            cikis  = model(xyz_tek)
            tahmin = cikis[0].argmax(dim=-1).cpu().numpy()  # [N]

        noktalar = xyz[0].numpy()  # [N, 3]

        # Renkleri ata
        renkler_gercek = np.array([SINIF_RENKLERI[int(e)] for e in gercek_tek])
        renkler_tahmin = np.array([SINIF_RENKLERI[int(t)] for t in tahmin])

        # Grafik: Sol = gerçek, Sağ = tahmin
        fig = plt.figure(figsize=(14, 6))
        fig.suptitle(f"Model #{ornek_no+1}", fontsize=14)

        for sutun, (renkler, baslik) in enumerate([
            (renkler_gercek, "Gerçek Etiketler"),
            (renkler_tahmin, "Model Tahmini")
        ]):
            ax = fig.add_subplot(1, 2, sutun+1, projection="3d")
            ax.scatter(
                noktalar[:, 0], noktalar[:, 1], noktalar[:, 2],
                c=renkler, s=1.5, alpha=0.7
            )
            ax.set_title(baslik)
            ax.set_axis_off()

        # Renk açıklaması
        legend_elementleri = [
            plt.Line2D([0], [0], marker="o", color="w",
                       markerfacecolor=SINIF_RENKLERI[s], markersize=10,
                       label=SINIF_ADLARI[s])
            for s in range(N_SINIF)
        ]
        fig.legend(handles=legend_elementleri, loc="lower center",
                   ncol=7, fontsize=9, bbox_to_anchor=(0.5, -0.02))

        plt.tight_layout()
        kayit_yolu = os.path.join(RAPOR_KLASORU, f"ornek_{ornek_no+1:02d}.png")
        plt.savefig(kayit_yolu, dpi=120, bbox_inches="tight")
        plt.close()
        print(f"  Kaydedildi: {kayit_yolu}")


# =============================================================================
# ANA DEĞERLENDIRME
# =============================================================================

def degerlendir():
    cihaz = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Cihaz: {cihaz}")

    # Model yükle
    print(f"\nModel yükleniyor: {MODEL_YOLU}")
    model = PointNet2Segmentasyon(n_sinif=N_SINIF).to(cihaz)
    model.load_state_dict(torch.load(MODEL_YOLU, map_location=cihaz))
    print("  Yüklendi.")

    # Test verisi
    _, test_loader = loader_olustur(NOKTA_KLASORU, batch_size=8)

    # Değerlendir
    print("\nTest seti değerlendiriliyor...")
    genel_dogr, sinif_dogr, ortalama_iou, sinif_iou = tam_degerlendir(model, test_loader, cihaz)

    # Rapor
    print("\n" + "=" * 55)
    print("  SONUÇLAR")
    print("=" * 55)
    print(f"  Genel doğruluk:  {genel_dogr*100:.2f}%")
    print(f"  Ortalama IoU:    {ortalama_iou*100:.2f}%")
    print()
    print(f"  {'Sınıf':>10}  {'Doğruluk':>10}  {'IoU':>10}")
    print("-" * 40)
    for s in range(N_SINIF):
        iou_str = f"{sinif_iou[s]*100:.1f}%" if not np.isnan(sinif_iou[s]) else "   -"
        print(f"  {SINIF_ADLARI[s]:>10}  {sinif_dogr[s]*100:>9.1f}%  {iou_str:>10}")
    print("=" * 55)

    # Hedef kontrolü
    if genel_dogr >= 0.89:
        print(f"\n  HEDEF AŞILDI! {genel_dogr*100:.1f}% ≥ %89")
    else:
        print(f"\n  Hedef: %89 | Mevcut: {genel_dogr*100:.1f}%")
        print("  İpucu: Daha fazla epoch ile eğitimi tekrar çalıştırın.")

    # Görseller
    print("\nÖrnek tahminler görselleştiriliyor...")
    gorsellestir(model, test_loader, cihaz, n_ornek=3)
    print(f"  Görseller kaydedildi: {RAPOR_KLASORU}/")


if __name__ == "__main__":
    degerlendir()

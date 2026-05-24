# =============================================================================
# FAZ 2 - ADIM 4: EĞİTİM
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA ÇALIŞTIRILIR.
#
# SIRA: 01 → 02 → 03 → [04_train.py] → 05
#
# NE YAPAR:
#   PointNet++ modelini 100 epoch boyunca eğitir.
#   Her epoch sonunda doğruluk ve kayıp değerini yazdırır.
#   En iyi modeli model_best.pth olarak kaydeder.
#   Eğitim bittinde model.pth kaydeder (son epoch).
#
# COLAB'DA ÇALIŞTIRMA:
#   1. Runtime → Change runtime type → GPU seç (T4 yeterli)
#   2. Sol panelden data/ ve faz2_egitim/ klasörlerini yükle
#   3. Bu dosyayı çalıştır
#   4. Bitti: data/processed/model_best.pth → indir → lorddoga'ya koy
#
# SÜRE TAHMİNİ:
#   GPU ile: ~30-60 dakika (100 epoch)
#   CPU ile: ~3-5 saat (sabırla bekleyin veya epoch azaltın)
# =============================================================================

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import os
import time

# Kendi dosyalarımızı import et
from faz2_egitim.o2_dataset import loader_olustur
from faz2_egitim.o3_pointnet2_model import PointNet2Segmentasyon

# =============================================================================
# AYARLAR
# =============================================================================

AYARLAR = {
    "nokta_klasoru":  "data/processed/pointclouds",
    "model_kayit":    "data/processed",
    "n_sinif":        7,
    "epoch":          100,
    "batch_size":     16,
    "ogrenme_hizi":   0.001,
    "lr_adim":        20,        # Her 20 epoch'ta öğrenme hızını azalt
    "lr_gama":        0.5,       # Azaltma oranı (0.5 = yarıya düşür)
    "test_orani":     0.15,
}

# Sınıf isimleri (rapor için)
SINIF_ADLARI = {0:"wall", 1:"floor", 2:"ceiling", 3:"door", 4:"window", 5:"roof", 6:"eave"}

# =============================================================================
# EĞİTİM FONKSİYONLARI
# =============================================================================

def epoch_egit(model, loader, optimizer, kayip_fonk, cihaz):
    """
    Bir epoch boyunca modeli eğitir.

    Döndürür: (ortalama_kayip, dogruluk)
    """
    model.train()   # Eğitim modu (BatchNorm ve Dropout aktif)

    toplam_kayip = 0.0
    dogru = 0
    toplam = 0

    for xyz, etiketler in loader:
        xyz      = xyz.to(cihaz)       # [B, N, 3]
        etiketler = etiketler.to(cihaz) # [B, N]

        # İleri geçiş
        optimizer.zero_grad()
        cikis = model(xyz)             # [B, N, n_sinif]

        # Kayıp hesapla
        # CrossEntropyLoss [B, C, N] formatı bekler
        cikis_2d = cikis.permute(0, 2, 1)   # [B, n_sinif, N]
        kayip = kayip_fonk(cikis_2d, etiketler)

        # Geri yayılım
        kayip.backward()
        optimizer.step()

        # İstatistik
        toplam_kayip += kayip.item()
        tahmin = cikis.argmax(dim=-1)  # [B, N]
        dogru  += (tahmin == etiketler).sum().item()
        toplam += etiketler.numel()

    return toplam_kayip / len(loader), dogru / toplam


def epoch_degerlendir(model, loader, kayip_fonk, cihaz):
    """
    Bir epoch boyunca modeli değerlendirir (eğitim yok).

    Döndürür: (ortalama_kayip, dogruluk, sinif_dogruluklari)
    """
    model.eval()   # Değerlendirme modu (BatchNorm sabit, Dropout kapalı)

    toplam_kayip = 0.0
    dogru = 0
    toplam = 0

    # Sınıf bazlı doğruluk için
    sinif_dogru  = np.zeros(AYARLAR["n_sinif"])
    sinif_toplam = np.zeros(AYARLAR["n_sinif"])

    with torch.no_grad():  # Gradyan hesaplama (bellek & hız için)
        for xyz, etiketler in loader:
            xyz       = xyz.to(cihaz)
            etiketler = etiketler.to(cihaz)

            cikis = model(xyz)
            cikis_2d = cikis.permute(0, 2, 1)
            kayip = kayip_fonk(cikis_2d, etiketler)

            toplam_kayip += kayip.item()
            tahmin = cikis.argmax(dim=-1)
            dogru  += (tahmin == etiketler).sum().item()
            toplam += etiketler.numel()

            # Sınıf bazlı
            for s in range(AYARLAR["n_sinif"]):
                maske = (etiketler == s)
                sinif_toplam[s] += maske.sum().item()
                sinif_dogru[s]  += (tahmin[maske] == s).sum().item()

    sinif_dogr = np.divide(
        sinif_dogru, sinif_toplam,
        out=np.zeros_like(sinif_dogru),
        where=sinif_toplam > 0
    )

    return toplam_kayip / len(loader), dogru / toplam, sinif_dogr


# =============================================================================
# ANA EĞİTİM DÖNGÜSÜ
# =============================================================================

def egit():
    # Cihaz seç (GPU varsa GPU, yoksa CPU)
    cihaz = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"  Cihaz: {cihaz}")
    if str(cihaz) == "cuda":
        print(f"  GPU: {torch.cuda.get_device_name(0)}")

    # Çıktı klasörü
    os.makedirs(AYARLAR["model_kayit"], exist_ok=True)

    # Veri yükleyiciler
    print("\nVeri yükleniyor...")
    train_loader, test_loader = loader_olustur(
        AYARLAR["nokta_klasoru"],
        batch_size=AYARLAR["batch_size"],
        test_orani=AYARLAR["test_orani"]
    )

    # Model
    print("Model oluşturuluyor...")
    model = PointNet2Segmentasyon(n_sinif=AYARLAR["n_sinif"]).to(cihaz)
    toplam_param = sum(p.numel() for p in model.parameters())
    print(f"  Toplam parametre: {toplam_param:,}")

    # Kayıp fonksiyonu: CrossEntropy (sınıf dengesizliği için ağırlıklı)
    # Kapı ve pencere daha az nokta içerir → daha yüksek ağırlık
    sinif_agirliklari = torch.tensor(
        [1.0, 2.0, 3.0, 20.0, 12.0, 1.0, 4.0],  # wall,floor,ceiling,door,window,roof,eave
        dtype=torch.float32
    ).to(cihaz)
    # door(~0.2% nokta) ve window(~4%) çok az temsil ediliyor → yüksek ağırlık şart
    kayip_fonk = nn.CrossEntropyLoss(weight=sinif_agirliklari)

    # Optimizer
    optimizer = optim.Adam(model.parameters(), lr=AYARLAR["ogrenme_hizi"])

    # Öğrenme hızı azaltma planı
    # Her lr_adim epoch'ta lr'yi lr_gama ile çarp
    scheduler = optim.lr_scheduler.StepLR(
        optimizer,
        step_size=AYARLAR["lr_adim"],
        gamma=AYARLAR["lr_gama"]
    )

    # Eğitim kaydı
    gecmis = {
        "train_kayip": [], "train_dogr": [],
        "test_kayip":  [], "test_dogr":  []
    }
    en_iyi_dogr = 0.0
    baslangic = time.time()

    print("\n" + "=" * 65)
    print(f"  EĞİTİM BAŞLIYOR — {AYARLAR['epoch']} EPOCH")
    print("=" * 65)
    print(f"  {'Epoch':>6}  {'Train Kayıp':>12}  {'Train Doğr':>10}  {'Test Doğr':>10}  {'Süre':>8}")
    print("-" * 65)

    for epoch in range(1, AYARLAR["epoch"] + 1):

        # Eğitim
        t_kayip, t_dogr = epoch_egit(model, train_loader, optimizer, kayip_fonk, cihaz)

        # Değerlendirme
        v_kayip, v_dogr, sinif_dogr = epoch_degerlendir(model, test_loader, kayip_fonk, cihaz)

        # Kayıt
        gecmis["train_kayip"].append(t_kayip)
        gecmis["train_dogr"].append(t_dogr)
        gecmis["test_kayip"].append(v_kayip)
        gecmis["test_dogr"].append(v_dogr)

        # LR güncelle
        scheduler.step()

        # Süre
        gecen = time.time() - baslangic
        dk, sn = divmod(int(gecen), 60)

        # Ekrana yaz
        print(f"  {epoch:>6}  {t_kayip:>12.4f}  {t_dogr*100:>9.2f}%  {v_dogr*100:>9.2f}%  {dk:>3}:{sn:02}", end="")

        # En iyi model
        if v_dogr > en_iyi_dogr:
            en_iyi_dogr = v_dogr
            yol = os.path.join(AYARLAR["model_kayit"], "model_best.pth")
            torch.save(model.state_dict(), yol)
            print("  ← EN İYİ", end="")

        print()

        # Her 10 epoch'ta sınıf bazlı rapor
        if epoch % 10 == 0:
            print(f"\n  --- Epoch {epoch} Sınıf Doğruluğu ---")
            for s in range(AYARLAR["n_sinif"]):
                ad = SINIF_ADLARI[s]
                print(f"    {ad:>10}: {sinif_dogr[s]*100:5.1f}%")
            print()

    # Son modeli kaydet
    yol_son = os.path.join(AYARLAR["model_kayit"], "model.pth")
    torch.save(model.state_dict(), yol_son)

    toplam_sure = time.time() - baslangic
    dk, sn = divmod(int(toplam_sure), 60)

    print("\n" + "=" * 65)
    print(f"  EĞİTİM TAMAMLANDI!")
    print(f"  Toplam süre:       {dk} dakika {sn} saniye")
    print(f"  En iyi test doğr:  {en_iyi_dogr*100:.2f}%")
    print(f"  Son model:         {yol_son}")
    print(f"  En iyi model:      {os.path.join(AYARLAR['model_kayit'], 'model_best.pth')}")
    print("=" * 65)
    print("\n  >> model_best.pth dosyasını indirip lorddoga/data/processed/ klasörüne koyun!")

    return gecmis, en_iyi_dogr


if __name__ == "__main__":
    gecmis, en_iyi = egit()

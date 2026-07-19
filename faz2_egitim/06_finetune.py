# =============================================================================
# FAZ 2 - ADIM 6: FINE-TUNE (mevcut modeli yeni veriyle ince ayar)
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA (GPU) veya yerel conda'da CALISTIRILIR.
#
# NE YAPAR:
#   04_train.py sifirdan egitir. Bu script FARKLI:
#   1. Onceden egitilmis model_best.pth'yi YUKLER (bastan baslamaz)
#   2. Yeni veri (v2 point cloud'lar) uzerinde DUSUK ogrenme hiziyla
#      kisa sure egitir -> "fine-tune / ince ayar"
#   3. Sonucu model_best.pth olarak kaydeder (segment_v2 otomatik okur)
#
# NEDEN DUSUK LR + AZ EPOCH?
#   Model zaten cogu seyi biliyor. Amac onu sifirlamak degil, yeni veriye
#   "hafifce" uyarlamak. Yuksek LR onceki bilgiyi siler (catastrophic forgetting).
#
# ON KOSUL:
#   - data/processed/pointclouds/  icinde .npy dosyalari olmali
#     (once 01_obj_to_pointcloud.py'yi v2 OBJ'lerle calistir)
#   - data/processed/model_best.pth  (fine-tune edilecek baslangic modeli)
#
# SIRA:
#   01 (v2 OBJ -> pointcloud) -> [06_finetune.py] -> yeni model_best.pth
# =============================================================================

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import os
import time

from faz2_egitim.o2_dataset import loader_olustur
from faz2_egitim.o3_pointnet2_model import PointNet2Segmentasyon

# =============================================================================
# AYARLAR
# =============================================================================

AYARLAR = {
    "nokta_klasoru":  "data/processed/pointclouds",   # v2 point cloud'lar
    "model_kayit":    "data/processed",
    "baslangic_model": "data/processed/model_best.pth",  # yuklenecek onceki model
    "n_sinif":        7,
    "epoch":          40,        # fine-tune icin az yeter (sifirdan degil)
    "batch_size":     16,
    "ogrenme_hizi":   0.0001,    # DUSUK! (04_train'de 0.001 idi) - 10x kucuk
    "test_orani":     0.15,
}

SINIF_ADLARI = {0:"wall", 1:"floor", 2:"ceiling", 3:"door", 4:"window", 5:"roof", 6:"eave"}


def epoch_egit(model, loader, optimizer, kayip_fonk, cihaz):
    model.train()
    toplam_kayip = 0.0
    dogru = 0
    toplam = 0
    for xyz, etiketler in loader:
        xyz = xyz.to(cihaz)
        etiketler = etiketler.to(cihaz)
        optimizer.zero_grad()
        cikis = model(xyz)
        cikis_2d = cikis.permute(0, 2, 1)
        kayip = kayip_fonk(cikis_2d, etiketler)
        kayip.backward()
        optimizer.step()
        toplam_kayip += kayip.item()
        tahmin = cikis.argmax(dim=-1)
        dogru += (tahmin == etiketler).sum().item()
        toplam += etiketler.numel()
    return toplam_kayip / len(loader), dogru / toplam


def epoch_degerlendir(model, loader, kayip_fonk, cihaz):
    model.eval()
    toplam_kayip = 0.0
    dogru = 0
    toplam = 0
    sinif_dogru = np.zeros(AYARLAR["n_sinif"])
    sinif_toplam = np.zeros(AYARLAR["n_sinif"])
    with torch.no_grad():
        for xyz, etiketler in loader:
            xyz = xyz.to(cihaz)
            etiketler = etiketler.to(cihaz)
            cikis = model(xyz)
            cikis_2d = cikis.permute(0, 2, 1)
            kayip = kayip_fonk(cikis_2d, etiketler)
            toplam_kayip += kayip.item()
            tahmin = cikis.argmax(dim=-1)
            dogru += (tahmin == etiketler).sum().item()
            toplam += etiketler.numel()
            for s in range(AYARLAR["n_sinif"]):
                maske = (etiketler == s)
                sinif_toplam[s] += maske.sum().item()
                sinif_dogru[s] += (tahmin[maske] == s).sum().item()
    sinif_dogr = np.divide(sinif_dogru, sinif_toplam,
                           out=np.zeros_like(sinif_dogru),
                           where=sinif_toplam > 0)
    return toplam_kayip / len(loader), dogru / toplam, sinif_dogr


def finetune():
    cihaz = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("  Cihaz:", cihaz)
    if str(cihaz) == "cuda":
        print("  GPU:", torch.cuda.get_device_name(0))

    os.makedirs(AYARLAR["model_kayit"], exist_ok=True)

    print("\nVeri yukleniyor...")
    train_loader, test_loader = loader_olustur(
        AYARLAR["nokta_klasoru"],
        batch_size=AYARLAR["batch_size"],
        test_orani=AYARLAR["test_orani"]
    )

    print("Model olusturuluyor...")
    model = PointNet2Segmentasyon(n_sinif=AYARLAR["n_sinif"]).to(cihaz)

    # --- FINE-TUNE FARKI: onceki agirliklari YUKLE ---
    bas_yol = AYARLAR["baslangic_model"]
    if os.path.exists(bas_yol):
        model.load_state_dict(torch.load(bas_yol, map_location=cihaz))
        print("  >> Baslangic modeli yuklendi:", bas_yol)
        print("     (Sifirdan degil, bu modelin uzerine ince ayar yapiliyor)")
    else:
        print("  !! UYARI:", bas_yol, "bulunamadi. SIFIRDAN egitilecek.")
        print("     Fine-tune istiyorsan once bu dosyayi yerine koy.")

    sinif_agirliklari = torch.tensor(
        [2.0, 3.0, 3.0, 4.0, 3.0, 1.0, 2.5],
        dtype=torch.float32
    ).to(cihaz)
    kayip_fonk = nn.CrossEntropyLoss(weight=sinif_agirliklari)

    optimizer = optim.Adam(model.parameters(), lr=AYARLAR["ogrenme_hizi"])
    scheduler = optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=AYARLAR["epoch"], eta_min=1e-6
    )

    # Baslangic dogrulugu (fine-tune oncesi referans)
    _, bas_dogr, _ = epoch_degerlendir(model, test_loader, kayip_fonk, cihaz)
    print("\n  Fine-tune ONCESI test dogrulugu: {:.2f}%".format(bas_dogr * 100))

    en_iyi_dogr = bas_dogr   # mevcut modelden kotuyse kaydetme
    baslangic = time.time()

    print("\n" + "=" * 65)
    print("  FINE-TUNE BASLIYOR - {} EPOCH  (lr={})".format(
        AYARLAR["epoch"], AYARLAR["ogrenme_hizi"]))
    print("=" * 65)
    print("  {:>6}  {:>12}  {:>10}  {:>10}  {:>8}".format(
        "Epoch", "Train Kayip", "Train Dogr", "Test Dogr", "Sure"))
    print("-" * 65)

    for epoch in range(1, AYARLAR["epoch"] + 1):
        t_kayip, t_dogr = epoch_egit(model, train_loader, optimizer, kayip_fonk, cihaz)
        v_kayip, v_dogr, sinif_dogr = epoch_degerlendir(model, test_loader, kayip_fonk, cihaz)
        scheduler.step()

        gecen = time.time() - baslangic
        dk, sn = divmod(int(gecen), 60)
        print("  {:>6}  {:>12.4f}  {:>9.2f}%  {:>9.2f}%  {:>3}:{:02}".format(
            epoch, t_kayip, t_dogr * 100, v_dogr * 100, dk, sn), end="")

        if v_dogr > en_iyi_dogr:
            en_iyi_dogr = v_dogr
            yol = os.path.join(AYARLAR["model_kayit"], "model_best.pth")
            torch.save(model.state_dict(), yol)
            print("  <- EN IYI", end="")
        print()

        if epoch % 10 == 0:
            print("\n  --- Epoch {} Sinif Dogrulugu ---".format(epoch))
            for s in range(AYARLAR["n_sinif"]):
                print("    {:>10}: {:5.1f}%".format(SINIF_ADLARI[s], sinif_dogr[s] * 100))
            print()

    # Fine-tune sonu modelini de ayri kaydet
    yol_son = os.path.join(AYARLAR["model_kayit"], "model_finetuned_son.pth")
    torch.save(model.state_dict(), yol_son)

    toplam_sure = time.time() - baslangic
    dk, sn = divmod(int(toplam_sure), 60)
    print("\n" + "=" * 65)
    print("  FINE-TUNE TAMAMLANDI!")
    print("  Sure:              {} dakika {} saniye".format(dk, sn))
    print("  Fine-tune oncesi:  {:.2f}%".format(bas_dogr * 100))
    print("  Fine-tune sonrasi: {:.2f}%  (en iyi)".format(en_iyi_dogr * 100))
    print("  Kaydedildi:        data/processed/model_best.pth")
    print("=" * 65)
    print("\n  >> model_best.pth otomatik guncellendi. Segment_v2 bunu kullanir.")

    return en_iyi_dogr


if __name__ == "__main__":
    finetune()

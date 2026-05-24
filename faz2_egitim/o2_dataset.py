# =============================================================================
# FAZ 2 - ADIM 2: PYTORCH DATASET SINIFI
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA ÇALIŞTIRILMAZ, 04_train.py TARAFINDAN KULLANILIR.
#
# NE YAPAR:
#   PyTorch'un veri yükleme sistemine (DataLoader) uyumlu bir Dataset sınıfı.
#   Eğitim sırasında her batch için otomatik olarak:
#   - Nokta bulutlarını diskten okur
#   - Veri artırma (augmentation) uygular: döndürme, ölçek, gürültü
#   - Tensöre çevirir
#
# NEDEN VERİ ARTIRMA (DATA AUGMENTATION)?
#   500 model az. Ağın her seferinde biraz farklı görmesi için
#   modelleri döndürüyoruz, ölçekliyoruz, gürültü ekliyoruz.
#   Bu sayede sanki binlerce farklı modelle eğitim yapılmış gibi olur.
#   → Daha iyi genelleme, daha yüksek doğruluk.
# =============================================================================

import numpy as np
import os
import torch
from torch.utils.data import Dataset, DataLoader


class MimariDataset(Dataset):
    """
    Mimari nokta bulutu segmentasyon veri seti.

    Kullanım:
        dataset = MimariDataset("data/processed/pointclouds", egitim=True)
        loader  = DataLoader(dataset, batch_size=16, shuffle=True)

        for xyz, etiketler in loader:
            # xyz:      [batch, 2048, 3]  → her noktanın x,y,z koordinatı
            # etiketler:[batch, 2048]     → her noktanın sınıf etiketi
            ...
    """

    def __init__(self, klasor, egitim=True, test_orani=0.15):
        """
        klasor:     Nokta bulutu .npy dosyalarının bulunduğu klasör
        egitim:     True → eğitim seti, False → test seti
        test_orani: Verinin yüzde kaçı test için ayrılacak
        """
        self.egitim = egitim

        # Tüm .npy dosyalarını listele
        dosyalar = sorted([
            os.path.join(klasor, f)
            for f in os.listdir(klasor)
            if f.endswith(".npy")
        ])

        if len(dosyalar) == 0:
            raise FileNotFoundError(
                f"'{klasor}' klasöründe .npy dosyası bulunamadı.\n"
                f"Önce 01_obj_to_pointcloud.py çalıştırın."
            )

        # Tekrarlanabilir train/test bölme
        np.random.seed(42)
        karistir = np.random.permutation(len(dosyalar))
        n_test = max(1, int(len(dosyalar) * test_orani))

        if egitim:
            secili = karistir[n_test:]   # Test dışındakiler eğitim
        else:
            secili = karistir[:n_test]   # İlk n_test adet test

        self.dosyalar = [dosyalar[i] for i in secili]

        print(f"  {'Eğitim' if egitim else 'Test'} seti: {len(self.dosyalar)} model")

    def __len__(self):
        """Veri setindeki toplam model sayısı."""
        return len(self.dosyalar)

    def __getitem__(self, idx):
        """
        idx numaralı modeli yükler ve döndürür.
        PyTorch DataLoader bu fonksiyonu otomatik çağırır.
        """
        veri = np.load(self.dosyalar[idx])   # [2048, 4] → [x, y, z, etiket]

        xyz      = veri[:, 0:3].copy()       # Koordinatlar
        etiketler = veri[:, 3].copy()         # Sınıf etiketleri

        # Eğitim sırasında veri artırma uygula
        if self.egitim:
            xyz = self._veri_artir(xyz)

        # Numpy → PyTorch tensör
        xyz       = torch.from_numpy(xyz.astype(np.float32))        # [2048, 3]
        etiketler = torch.from_numpy(etiketler.astype(np.int64))    # [2048]

        return xyz, etiketler

    def _veri_artir(self, xyz):
        """
        Eğitim sırasında nokta bulutunu rastgele dönüştürür.

        1. Z ekseni etrafında döndür → bina farklı yönlerden görülür
        2. Ölçeği hafifçe değiştir → farklı bina boyutları simüle edilir
        3. Küçük gürültü ekle → sensör hatası, mesh hassasiyeti simüle edilir
        """

        # 1. Z ekseni etrafında rastgele 90° katları döndür
        aci = np.random.choice([0, 90, 180, 270])
        aci_rad = np.radians(aci)
        donme_matrisi = np.array([
            [np.cos(aci_rad), -np.sin(aci_rad), 0],
            [np.sin(aci_rad),  np.cos(aci_rad), 0],
            [0,                0,               1]
        ], dtype=np.float32)
        xyz = xyz @ donme_matrisi.T

        # 2. Rastgele ölçek (±10%)
        olcek = np.random.uniform(0.9, 1.1)
        xyz *= olcek

        # 3. Küçük Gaussian gürültü
        gurultu = np.random.normal(0, 0.005, xyz.shape).astype(np.float32)
        xyz += gurultu

        # Normalize et (ölçek değiştiğinden tekrar birim küre)
        merkez = xyz.mean(axis=0)
        xyz -= merkez
        en_uzak = np.max(np.sqrt(np.sum(xyz ** 2, axis=1)))
        if en_uzak > 0:
            xyz /= en_uzak

        return xyz


def loader_olustur(klasor, batch_size=16, test_orani=0.15):
    """
    Eğitim ve test DataLoader'larını oluşturur.

    Döndürür:
        train_loader: Eğitim için (shuffle=True, veri artırma açık)
        test_loader:  Test için  (shuffle=False, veri artırma kapalı)
    """
    train_set = MimariDataset(klasor, egitim=True,  test_orani=test_orani)
    test_set  = MimariDataset(klasor, egitim=False, test_orani=test_orani)

    train_loader = DataLoader(
        train_set,
        batch_size=batch_size,
        shuffle=True,         # Her epoch'ta karıştır
        num_workers=0,        # Colab'da 0 önerilir
        drop_last=True        # Son yarım batch'i atla (boyut tutarsızlığı önler)
    )

    test_loader = DataLoader(
        test_set,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0
    )

    return train_loader, test_loader


# Test: Bu dosyayı direkt çalıştırırsanız veri setini kontrol eder
if __name__ == "__main__":
    KLASOR = "data/processed/pointclouds"

    print("Veri seti yükleniyor...")
    train_loader, test_loader = loader_olustur(KLASOR, batch_size=4)

    print(f"\n  Train batch sayısı: {len(train_loader)}")
    print(f"  Test  batch sayısı: {len(test_loader)}")

    # İlk batch'e bak
    xyz, etiketler = next(iter(train_loader))
    print(f"\n  İlk batch:")
    print(f"    xyz boyutu:       {xyz.shape}        → [batch, nokta, 3]")
    print(f"    etiketler boyutu: {etiketler.shape}  → [batch, nokta]")
    print(f"    xyz değer aralığı: [{xyz.min():.2f}, {xyz.max():.2f}]")
    print(f"    Sınıflar: {etiketler.unique().tolist()}")

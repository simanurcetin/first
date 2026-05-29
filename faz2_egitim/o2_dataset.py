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
        veri = np.load(self.dosyalar[idx])   # [2048, 7] → [x, y, z, nx, ny, nz, etiket]

        xyz     = veri[:, 0:3].copy()        # Koordinatlar
        normaller = veri[:, 3:6].copy()      # Normal vektörler
        etiketler = veri[:, 6].copy()        # Sınıf etiketleri

        # Eğitim sırasında veri artırma uygula (xyz + normaller birlikte döndürülür)
        if self.egitim:
            xyz, normaller = self._veri_artir(xyz, normaller)
            xyz, normaller, etiketler = self._nokta_dropout(xyz, normaller, etiketler)

        # xyz ve normalleri birleştir → [2048, 6]
        xyz_normal = np.concatenate([xyz, normaller], axis=1).astype(np.float32)

        # Numpy → PyTorch tensör
        xyz_normal = torch.from_numpy(xyz_normal)               # [2048, 6]
        etiketler  = torch.from_numpy(etiketler.astype(np.int64))  # [2048]

        return xyz_normal, etiketler

    def _veri_artir(self, xyz, normaller):
        """
        Eğitim sırasında nokta bulutunu rastgele dönüştürür.
        Normal vektörler de aynı rotasyona tabi tutulur.

        Meshy AI gibi "alan dışı" modellere genelleme için güçlü augmentation:
          - Tam 360° Z dönüşü (bina yönü farklı gelebilir)
          - Her eksen ayrı ölçek (farklı bina oranları)
          - Küçük X/Y eğimi (modelin tam dik gelmeme durumu)
          - Güçlü xyz + normal gürültüsü (organik/gürültülü mesh)
        """
        # 1. Z ekseni etrafında tam 360° döndür
        aci = np.random.uniform(0, 2 * np.pi)
        cz, sz = np.cos(aci), np.sin(aci)
        Rz = np.array([[cz, -sz, 0],
                       [sz,  cz, 0],
                       [0,   0,  1]], dtype=np.float32)
        xyz       = xyz @ Rz.T
        normaller = normaller @ Rz.T

        # 2. Küçük X/Y eğimi (±8°) — zemin/tavan normalini fazla bozmaz
        for eksen in [0, 1]:
            egim = np.random.uniform(-0.14, 0.14)   # ~±8 derece
            c, s = np.cos(egim), np.sin(egim)
            if eksen == 0:   # X ekseni etrafında
                R = np.array([[1, 0, 0],
                              [0, c, -s],
                              [0, s,  c]], dtype=np.float32)
            else:            # Y ekseni etrafında
                R = np.array([[ c, 0, s],
                              [ 0, 1, 0],
                              [-s, 0, c]], dtype=np.float32)
            xyz       = xyz @ R.T
            normaller = normaller @ R.T

        # 3. Anizotropik ölçek — her eksen bağımsız (farklı bina oranları)
        for k in range(3):
            xyz[:, k] *= np.random.uniform(0.75, 1.25)

        # 4. Güçlü xyz gürültüsü (organik/gürültülü mesh'lere dayanıklılık)
        xyz += np.random.normal(0, 0.015, xyz.shape).astype(np.float32)

        # 5. Normal vektörlere hafif gürültü (normalize et sonrasında)
        normaller += np.random.normal(0, 0.05, normaller.shape).astype(np.float32)
        uzunluk = np.linalg.norm(normaller, axis=1, keepdims=True)
        uzunluk = np.where(uzunluk > 0, uzunluk, 1.0)
        normaller /= uzunluk

        # 6. xyz'yi yeniden normalize et (birim küre)
        xyz -= xyz.mean(axis=0)
        en_uzak = np.max(np.sqrt(np.sum(xyz ** 2, axis=1)))
        if en_uzak > 0:
            xyz /= en_uzak

        return xyz, normaller

    def _nokta_dropout(self, xyz, normaller, etiketler, oran=0.1):
        """
        Noktaların rastgele bir kısmını düşürür, yerine var olan noktaları kopyalar.
        Delikli/seyrek/eksik mesh'lere dayanıklılık sağlar.
        Beklenen dropout: %0–10 arası rastgele.
        """
        n = len(xyz)
        gercek_oran = np.random.uniform(0, oran)
        n_dusur = int(n * gercek_oran)
        if n_dusur == 0:
            return xyz, normaller, etiketler

        # Düşürülecek indeksler
        dusur = np.random.choice(n, size=n_dusur, replace=False)
        # Onların yerine kalan noktalardan rastgele kopyala
        kalan = np.setdiff1d(np.arange(n), dusur)
        kopyalar = np.random.choice(kalan, size=n_dusur, replace=True)

        xyz[dusur]       = xyz[kopyalar]
        normaller[dusur] = normaller[kopyalar]
        etiketler[dusur] = etiketler[kopyalar]

        return xyz, normaller, etiketler


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

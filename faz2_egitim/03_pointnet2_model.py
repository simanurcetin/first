# =============================================================================
# FAZ 2 - ADIM 3: POINTNET++ MODEL MİMARİSİ
# =============================================================================
#
# BU DOSYA GOOGLE COLAB'DA ÇALIŞTIRILMAZ, 04_train.py TARAFINDAN KULLANILIR.
#
# NE YAPAR:
#   PointNet++ (PointNet2) derin öğrenme modelini tanımlar.
#   Giriş: [batch, 2048, 3] → 2048 noktanın x,y,z koordinatları
#   Çıkış: [batch, 2048, 7] → her noktanın 7 sınıfa ait olasılıkları
#
# POINTNET++ NEDİR?
#   2017'de Stanford'da geliştirilen 3D nokta bulutu işleme ağı.
#   Normal CNN'ler düzenli grid (piksel) üzerinde çalışır.
#   PointNet++ ise düzensiz yerleştirilmiş 3D noktalar üzerinde çalışır.
#
#   İki aşaması var:
#   1. ENCODER (Aşağı örnekleme): Noktaları gruplar, özellik çıkarır
#      - Set Abstraction: Noktaları birleştir, özellik özetle
#   2. DECODER (Yukarı örnekleme): Özellikleri tüm noktalara yay
#      - Feature Propagation: Seyrek özellikleri yoğun noktaya yay
#
#   Mimari olarak U-Net'e benzer (tıpta yaygın).
#
# CUDA EKSTANSİYONU GEREKTİRMEZ:
#   Bazı PointNet++ implementasyonları özel CUDA kodu gerektirir.
#   Bu implementasyon tamamen standart PyTorch kullanır → Colab'da sorunsuz çalışır.
# =============================================================================

import torch
import torch.nn as nn
import torch.nn.functional as F


# =============================================================================
# TEMEL OPERASYONLAR
# =============================================================================

def en_uzak_nokta_ornekle(xyz, n_nokta):
    """
    Farthest Point Sampling (FPS): En yayılmış n_nokta noktayı seçer.

    Neden önemli?
    Rastgele örnekleme bir bölgeye kümelenebilir.
    FPS her seferinde mevcut noktalara en uzak noktayı seçer →
    seçilen noktalar modelin her yerini dengeli temsil eder.

    xyz:     [B, N, 3] → B: batch boyutu, N: nokta sayısı
    n_nokta: Seçilecek merkez nokta sayısı
    Döndürür: [B, n_nokta] → seçilen noktaların indeksleri
    """
    B, N, _ = xyz.shape
    cihaz = xyz.device

    secilen = torch.zeros(B, n_nokta, dtype=torch.long, device=cihaz)
    mesafe  = torch.full((B, N), 1e10, device=cihaz)

    # Her batch için rastgele bir başlangıç noktası
    en_uzak = torch.randint(0, N, (B,), dtype=torch.long, device=cihaz)

    for i in range(n_nokta):
        secilen[:, i] = en_uzak

        # Seçilen noktanın koordinatları: [B, 1, 3]
        merkez = xyz[torch.arange(B, device=cihaz), en_uzak, :].unsqueeze(1)

        # Tüm noktalara uzaklık: [B, N]
        uzaklik = torch.sum((xyz - merkez) ** 2, dim=-1)

        # Her nokta için minimum uzaklığı güncelle
        mesafe = torch.min(mesafe, uzaklik)

        # En uzak noktayı seç
        en_uzak = mesafe.argmax(dim=1)

    return secilen


def knn_sorgula(k, xyz, merkez_xyz):
    """
    Her merkez nokta için k en yakın komşuyu bulur (kNN).

    PointNet++'ın orijinalinde "ball query" (yarıçap içindeki noktalar) kullanılır.
    Biz kNN kullanıyoruz → CUDA extension gerektirmiyor, benzer sonuç verir.

    xyz:        [B, N, 3] → tüm noktalar
    merkez_xyz: [B, S, 3] → merkez noktalar
    k:          Komşu sayısı
    Döndürür: [B, S, k] → her merkez için k komşu indeksi
    """
    B, N, _ = xyz.shape
    S = merkez_xyz.shape[1]

    # Pairwise uzaklık matrisi: [B, S, N]
    # ||a-b||² = ||a||² + ||b||² - 2*a·b
    merkez_kare = torch.sum(merkez_xyz ** 2, dim=-1, keepdim=True)   # [B, S, 1]
    xyz_kare    = torch.sum(xyz ** 2, dim=-1, keepdim=True)           # [B, N, 1]
    carpim      = torch.bmm(merkez_xyz, xyz.transpose(1, 2))          # [B, S, N]

    uzaklik = merkez_kare + xyz_kare.transpose(1, 2) - 2 * carpim    # [B, S, N]
    uzaklik = torch.clamp(uzaklik, min=0)  # Sayısal hata için

    # En yakın k noktanın indekslerini al
    _, indeksler = uzaklik.topk(k, dim=-1, largest=False)             # [B, S, k]
    return indeksler


def noktalar_topla(xyz, indeksler):
    """
    İndekslere göre nokta koordinatlarını toplar.

    xyz:      [B, N, C]
    indeksler:[B, S, k]
    Döndürür: [B, S, k, C]
    """
    B, N, C = xyz.shape
    S, k = indeksler.shape[1], indeksler.shape[2]

    # indeksler: [B, S, k] → [B, S*k]
    duz_indeks = indeksler.view(B, -1)

    # Batch indeksi: [B, 1] → yayılır → [B, S*k]
    batch_indeks = torch.arange(B, device=xyz.device).unsqueeze(1).expand(-1, S * k)

    # Topla: [B, S*k, C]
    toplanan = xyz[batch_indeks, duz_indeks, :]

    # Şekillendi: [B, S, k, C]
    return toplanan.view(B, S, k, C)


# =============================================================================
# SET ABSTRACTION (SA) KATMANI
# Encoder'ın temel bloğu: noktaları örnekle, grupla, özellik çıkar
# =============================================================================

class SetAbstraction(nn.Module):
    """
    PointNet++ Set Abstraction katmanı.

    Ne yapar:
    1. FPS ile merkez noktalar seç (N noktadan npoint noktaya düşür)
    2. Her merkeze en yakın k komşuyu bul
    3. Komşu noktalar üzerinde MLP çalıştır → lokal özellik
    4. Max pooling ile her merkez için tek özellik vektörü üret

    npoint: Çıkacak merkez nokta sayısı (örnekleme oranı)
    k:      Her merkez için komşu sayısı
    in_ch:  Giriş özellik boyutu
    mlp:    MLP katman boyutları listesi
    """

    def __init__(self, npoint, k, in_ch, mlp):
        super().__init__()
        self.npoint = npoint
        self.k = k

        # MLP katmanları (1D convolution = her nokta için aynı ağırlıklar)
        katmanlar = []
        onceki = in_ch
        for cikis in mlp:
            katmanlar += [
                nn.Conv2d(onceki, cikis, 1),
                nn.BatchNorm2d(cikis),
                nn.ReLU()
            ]
            onceki = cikis
        self.mlp = nn.Sequential(*katmanlar)
        self.cikis_boyutu = mlp[-1]

    def forward(self, xyz, ozellik=None):
        """
        xyz:     [B, N, 3]   → nokta koordinatları
        ozellik: [B, N, C]   → önceki katmandan gelen özellikler (opsiyonel)

        Döndürür:
            yeni_xyz:     [B, npoint, 3]   → örneklenmiş merkez noktalar
            yeni_ozellik: [B, npoint, mlp_son] → çıkarılan özellikler
        """
        B, N, _ = xyz.shape

        # 1. FPS ile merkez noktaları seç
        fps_idx   = en_uzak_nokta_ornekle(xyz, self.npoint)        # [B, npoint]
        batch_idx = torch.arange(B, device=xyz.device).unsqueeze(1).expand(-1, self.npoint)
        yeni_xyz  = xyz[batch_idx, fps_idx, :]                      # [B, npoint, 3]

        # 2. Her merkeze en yakın k komşuyu bul
        komsu_idx = knn_sorgula(self.k, xyz, yeni_xyz)              # [B, npoint, k]

        # 3. Komşu koordinatları topla ve merkezden farkı al
        komsu_xyz = noktalar_topla(xyz, komsu_idx)                  # [B, npoint, k, 3]
        komsu_xyz -= yeni_xyz.unsqueeze(2)                          # Merkeze göre relatif

        # 4. Varsa önceki özellikleri ekle
        if ozellik is not None:
            komsu_feat = noktalar_topla(ozellik, komsu_idx)         # [B, npoint, k, C]
            giris = torch.cat([komsu_xyz, komsu_feat], dim=-1)      # [B, npoint, k, 3+C]
        else:
            giris = komsu_xyz                                        # [B, npoint, k, 3]

        # 5. MLP uygula: [B, npoint, k, C] → [B, C, npoint, k]
        giris = giris.permute(0, 3, 1, 2)
        cikis = self.mlp(giris)                                      # [B, mlp_son, npoint, k]

        # 6. Max pooling: k komşu → 1 özellik
        cikis = cikis.max(dim=-1)[0]                                 # [B, mlp_son, npoint]
        cikis = cikis.permute(0, 2, 1)                               # [B, npoint, mlp_son]

        return yeni_xyz, cikis


# =============================================================================
# FEATURE PROPAGATION (FP) KATMANI
# Decoder'ın temel bloğu: seyrek özellikleri yoğun noktalara yay
# =============================================================================

class FeaturePropagation(nn.Module):
    """
    PointNet++ Feature Propagation katmanı.

    Encoder'da azaltılan nokta sayısını geri artırır.
    Interpolasyon + skip connection kullanır (U-Net'e benzer).

    in_ch: Giriş özellik boyutu (interpolasyon + skip connection toplamı)
    mlp:   MLP katman boyutları
    """

    def __init__(self, in_ch, mlp):
        super().__init__()
        katmanlar = []
        onceki = in_ch
        for cikis in mlp:
            katmanlar += [
                nn.Conv1d(onceki, cikis, 1),
                nn.BatchNorm1d(cikis),
                nn.ReLU()
            ]
            onceki = cikis
        self.mlp = nn.Sequential(*katmanlar)

    def forward(self, xyz1, xyz2, feat1, feat2):
        """
        xyz1:  [B, N, 3]  → hedef noktalar (daha yoğun, encoder'da önceki katman)
        xyz2:  [B, S, 3]  → kaynak noktalar (daha seyrek, encoder'da sonraki katman)
        feat1: [B, N, C1] → skip connection özellikleri (encoder'dan)
        feat2: [B, S, C2] → yayılacak özellikler

        Döndürür: [B, N, mlp_son]
        """
        B, N, _ = xyz1.shape
        S = xyz2.shape[1]

        if S == 1:
            # Tek nokta → hepsine aynı özelliği ver
            interpolated = feat2.expand(B, N, -1)
        else:
            # 3 en yakın komşudan ağırlıklı interpolasyon
            k = min(3, S)
            komsu_idx = knn_sorgula(k, xyz2, xyz1)                  # [B, N, k]

            # Uzaklıkları hesapla
            komsu_xyz = noktalar_topla(xyz2, komsu_idx)              # [B, N, k, 3]
            uzaklik   = torch.sum((xyz1.unsqueeze(2) - komsu_xyz) ** 2, dim=-1)  # [B, N, k]
            uzaklik   = torch.clamp(uzaklik, min=1e-10)
            agirlik   = 1.0 / uzaklik                                # Yakın = yüksek ağırlık
            agirlik   = agirlik / agirlik.sum(dim=-1, keepdim=True)  # Normalize

            # Komşu özellikleri topla
            komsu_feat = noktalar_topla(feat2, komsu_idx)            # [B, N, k, C2]
            interpolated = (agirlik.unsqueeze(-1) * komsu_feat).sum(dim=2)  # [B, N, C2]

        # Skip connection ile birleştir
        if feat1 is not None:
            yeni_feat = torch.cat([feat1, interpolated], dim=-1)     # [B, N, C1+C2]
        else:
            yeni_feat = interpolated

        # MLP
        yeni_feat = yeni_feat.permute(0, 2, 1)                       # [B, C, N]
        yeni_feat = self.mlp(yeni_feat)                               # [B, mlp_son, N]
        yeni_feat = yeni_feat.permute(0, 2, 1)                       # [B, N, mlp_son]

        return yeni_feat


# =============================================================================
# TAM POINTNET++ SEGMENTASYON AĞINIZIN
# =============================================================================

class PointNet2Segmentasyon(nn.Module):
    """
    PointNet++ tabanlı mimari segmentasyon ağı.

    Giriş: [B, N, 3]    → N nokta, her biri (x,y,z)
    Çıkış: [B, N, n_sinif] → her noktanın sınıf logitleri

    Mimari (U-Net benzeri encoder-decoder):

    Encoder:
      SA1: 2048 → 512 nokta  (lokal küçük özellikler)
      SA2: 512  → 128 nokta  (orta ölçek özellikler)
      SA3: 128  → 32 nokta   (büyük ölçek özellikler)

    Decoder:
      FP3: 32  → 128 nokta   (özellik yay)
      FP2: 128 → 512 nokta   (özellik yay)
      FP1: 512 → 2048 nokta  (tüm noktalara geri dön)

    Sınıflandırıcı:
      Linear(128, 64) → Linear(64, n_sinif)
    """

    def __init__(self, n_sinif=7):
        super().__init__()
        self.n_sinif = n_sinif

        # --- ENCODER ---
        # (npoint, k, in_ch, mlp)
        self.sa1 = SetAbstraction(npoint=512, k=32, in_ch=3,   mlp=[32, 32, 64])
        self.sa2 = SetAbstraction(npoint=128, k=32, in_ch=3+64, mlp=[64, 64, 128])
        self.sa3 = SetAbstraction(npoint=32,  k=16, in_ch=3+128,mlp=[128, 128, 256])

        # --- DECODER ---
        # (in_ch = üst katman özelliği + skip connection özelliği)
        self.fp3 = FeaturePropagation(in_ch=256+128, mlp=[256, 128])
        self.fp2 = FeaturePropagation(in_ch=128+64,  mlp=[128, 64])
        self.fp1 = FeaturePropagation(in_ch=64+0,    mlp=[64, 64])

        # --- SINIFLANDIRICI ---
        self.siniflandirici = nn.Sequential(
            nn.Conv1d(64, 64, 1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(0.4),
            nn.Conv1d(64, n_sinif, 1)
        )

    def forward(self, xyz):
        """
        xyz: [B, N, 3]
        Döndürür: [B, N, n_sinif] → her noktanın sınıf skorları (softmax öncesi)
        """
        B, N, _ = xyz.shape

        # === ENCODER ===
        xyz1, feat1 = self.sa1(xyz)           # [B,512,3], [B,512,64]
        xyz2, feat2 = self.sa2(xyz1, feat1)   # [B,128,3], [B,128,128]
        xyz3, feat3 = self.sa3(xyz2, feat2)   # [B,32,3],  [B,32,256]

        # === DECODER ===
        feat2_up = self.fp3(xyz2, xyz3, feat2, feat3)   # [B,128,128]
        feat1_up = self.fp2(xyz1, xyz2, feat1, feat2_up) # [B,512,64]
        feat0_up = self.fp1(xyz,  xyz1, None,  feat1_up) # [B,N,64]

        # === SINIFLANDIRICI ===
        cikis = feat0_up.permute(0, 2, 1)               # [B, 64, N]
        cikis = self.siniflandirici(cikis)               # [B, n_sinif, N]
        cikis = cikis.permute(0, 2, 1)                   # [B, N, n_sinif]

        return cikis


# Test: Modelin boyutları doğru mu?
if __name__ == "__main__":
    print("Model testi...")
    model = PointNet2Segmentasyon(n_sinif=7)

    # Parametre sayısı
    toplam = sum(p.numel() for p in model.parameters())
    print(f"  Toplam parametre: {toplam:,}  (~{toplam/1e6:.1f}M)")

    # İleri geçiş testi
    ornek = torch.randn(2, 512, 3)   # Küçük test: 2 batch, 512 nokta
    with torch.no_grad():
        cikis = model(ornek)

    print(f"  Giriş boyutu:  {ornek.shape}   → [batch, nokta, 3]")
    print(f"  Çıkış boyutu:  {cikis.shape} → [batch, nokta, sinif_sayisi]")
    print("  Model çalışıyor!")

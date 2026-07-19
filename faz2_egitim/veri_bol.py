# -*- coding: utf-8 -*-
# =============================================================================
# VERI BOLME: 802 OBJ -> 702 train + 100 test (temiz ayrim)
# =============================================================================
#
# Test dosyalari egitime ASLA girmez. Boylece dogruluk olcumu durust olur.
# Kopyalar (orijinal obj_files dokunulmadan kalir), sabit seed ile tekrar
# edilebilir (her calistirmada ayni 100 test dosyasi).
#
# CALISTIRMA:
#   conda run -n mimari_ai python faz2_egitim/veri_bol.py
# =============================================================================

import os
import random
import shutil

# --- KLASORLER (kendi yoluna gore ayarla) ---
KAYNAK      = r"C:\Users\siman\OneDrive\Masaüstü\first\data_v2_test\obj_files"
TRAIN_HEDEF = r"C:\Users\siman\OneDrive\Masaüstü\first\data_v2_test\train_702"
TEST_HEDEF  = r"C:\Users\siman\OneDrive\Masaüstü\first\data_v2_test\test_100"
TEST_ADET   = 100

random.seed(42)   # tekrar edilebilir bolme (ayni 100 test her zaman)

# Tum obj dosyalari
tum = sorted([f for f in os.listdir(KAYNAK) if f.lower().endswith(".obj")])
print("Toplam obj:", len(tum))

# Hedef klasorleri olustur
for h in (TRAIN_HEDEF, TEST_HEDEF):
    if not os.path.isdir(h):
        os.makedirs(h)

# Rastgele TEST_ADET tanesini test'e ayir, geri kalani train
test_dosyalar = set(random.sample(tum, min(TEST_ADET, len(tum))))
train_dosyalar = [f for f in tum if f not in test_dosyalar]

# Kopyala
for ad in test_dosyalar:
    shutil.copy2(os.path.join(KAYNAK, ad), os.path.join(TEST_HEDEF, ad))
for ad in train_dosyalar:
    shutil.copy2(os.path.join(KAYNAK, ad), os.path.join(TRAIN_HEDEF, ad))

print("Test  :", len(test_dosyalar), "->", TEST_HEDEF)
print("Train :", len(train_dosyalar), "->", TRAIN_HEDEF)
print("\nTamam! Test dosyalari egitime girmeyecek (temiz ayrim).")

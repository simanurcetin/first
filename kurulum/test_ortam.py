"""
Conda ortamının doğru kurulduğunu test eder.
Her kütüphane için yeşil onay veya kırmızı hata gösterir.
"""
import sys

def test(isim, kod):
    try:
        exec(kod)
        print(f"  [OK]  {isim}")
        return True
    except Exception as e:
        print(f"  [HATA] {isim}: {e}")
        return False

print("=" * 50)
print("  ORTAM TESTİ")
print("=" * 50)
print(f"  Python: {sys.version.split()[0]}")
print()

sonuclar = [
    test("torch (PyTorch)",     "import torch; print(f'         versiyon: {torch.__version__}')"),
    test("numpy",               "import numpy; print(f'         versiyon: {numpy.__version__}')"),
    test("open3d",              "import open3d; print(f'         versiyon: {open3d.__version__}')"),
    test("trimesh",             "import trimesh; print(f'         versiyon: {trimesh.__version__}')"),
    test("sklearn",             "import sklearn; print(f'         versiyon: {sklearn.__version__}')"),
    test("matplotlib",          "import matplotlib; print(f'         versiyon: {matplotlib.__version__}')"),
    test("tqdm",                "import tqdm; print(f'         versiyon: {tqdm.__version__}')"),
    test("pandas",              "import pandas; print(f'         versiyon: {pandas.__version__}')"),
    test("GPU (opsiyonel)",     "import torch; gpu=torch.cuda.is_available(); print(f'         GPU: {\"VAR\" if gpu else \"YOK (CPU kullanılacak)\"}')")
]

print()
basarili = sum(sonuclar)
print(f"  Sonuç: {basarili}/{len(sonuclar)} test geçti")

if basarili == len(sonuclar):
    print("  Tüm testler geçti! Projeye başlayabilirsiniz.")
else:
    print("  Bazı kütüphaneler eksik. 1_KURULUM.bat tekrar çalıştırın.")
print("=" * 50)

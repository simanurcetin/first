# =============================================================================
# FAZ 1 - SENTETİK BİNA MODELİ ÜRETİCİ
# =============================================================================
#
# BU DOSYA GRASSHOPPER'IN "PYTHON SCRIPT" BİLEŞENİNE YAPIŞTIRILIR.
#
# NASIL KULLANILIR:
#   1. Rhino + Grasshopper'ı açın
#   2. Grasshopper'a bir "Python Script" bileşeni sürükleyin
#   3. Bu dosyanın tüm içeriğini kopyalayıp yapıştırın
#   4. Bileşene sağ tıklayın → "Run" veya bileşeni etkinleştirin
#   5. Script çalışınca data/obj_files ve data/json_files klasörlerini dolduracak
#
# ÇIKTI:
#   - 500 adet  .obj  dosyası  (3D geometri - yüzeyler)
#   - 500 adet  .json dosyası  (hangi yüzey hangi sınıf: wall/floor/window...)
#
# IronPython KISITLAMALARI (Grasshopper içinde):
#   ✓ rhinoscriptsyntax  → Rhino nesneleri
#   ✓ Rhino.Geometry     → Nokta, vektör, mesh
#   ✓ math               → sin, cos, pi, sqrt
#   ✓ json               → dosya yazma
#   ✓ random             → rastgelelik
#   ✓ os                 → klasör oluşturma
#   ✗ numpy, scipy, pip  → KULLANILAMAZ
#
# SEMANTİK SINIFLAR (7 adet, config.json ile uyumlu):
#   0 = wall    (duvar)
#   1 = floor   (döşeme)
#   2 = ceiling (tavan)
#   3 = door    (kapı)
#   4 = window  (pencere)
#   5 = roof    (çatı)
#   6 = eave    (saçak)
# =============================================================================

import rhinoscriptsyntax as rs   # Rhino çizim fonksiyonları
import Rhino.Geometry as rg      # Düşük seviye geometri: Point3d, Mesh...
import math                       # Trigonometri (sin, cos, pi)
import json                       # JSON dosya kaydetme
import random                     # Rastgele sayı üretimi
import os                         # Klasör oluşturma, dosya yolu

# =============================================================================
# AYARLAR - Buradaki değerleri değiştirerek üretimi özelleştirebilirsiniz
# =============================================================================

# Kaç model üretilecek?
MODEL_SAYISI = 500

# Dosyaların kaydedileceği klasörler
#
# Grasshopper'da __file__ çalışmaz, bu yüzden yolu 3 yöntemle bulmaya çalışıyoruz:
#   Yöntem 1: Rhino belgesi kaydedilmişse onun klasörünü kullan
#   Yöntem 2: Masaüstündeki lorddoga klasörünü kullan
#   Yöntem 3: Aşağıdaki SABIT_YOL satırını açıp kendi yolunuzu yazın
#
import Rhino as _Rhino

_sabit_yol = ""   # ← Otomatik bulunamazsa buraya yazın: r"C:\Users\ADINIZ\Desktop\lorddoga"

def _proje_klasoru_bul():
    # Yöntem 1: Açık Rhino belgesi kaydedilmişse
    try:
        _doc_yol = _Rhino.RhinoDoc.ActiveDoc.Path
        if _doc_yol:
            return os.path.dirname(_doc_yol)
    except:
        pass
    # Yöntem 2: Sabit yol tanımlanmışsa
    if _sabit_yol:
        return _sabit_yol
    # Yöntem 3: Masaüstü\lorddoga (varsayılan)
    return os.path.join(os.environ.get("USERPROFILE", "C:\\Users\\User"), "Desktop", "lorddoga")

_PROJE = _proje_klasoru_bul()
OBJ_KLASORU  = os.path.join(_PROJE, "data", "obj_files")
JSON_KLASORU = os.path.join(_PROJE, "data", "json_files")

# Rastgelelik için tohum - aynı tohum = aynı modeller (tekrarlanabilirlik)
TOHUM = 42

# Semantik sınıf kimlikleri
SINIF = {
    "wall":    0,   # duvar
    "floor":   1,   # döşeme
    "ceiling": 2,   # tavan
    "door":    3,   # kapı
    "window":  4,   # pencere
    "roof":    5,   # çatı
    "eave":    6,   # saçak
}

# =============================================================================
# YARDIMCI: MESH OLUŞTURMA FONKSİYONLARI
# (IronPython'da numpy yok, elle yapıyoruz)
# =============================================================================

def yeni_mesh():
    """Boş bir Rhino Mesh nesnesi oluşturur."""
    return rg.Mesh()

def mesh_e_quad_ekle(mesh, p0, p1, p2, p3):
    """
    4 köşeli bir yüzey (quad face) ekler.
    p0-p3: rg.Point3d nesneleri (x, y, z koordinatları)

    Quad = dörtgen yüzey. Bina modellerinde duvarlar, pencereler
    hep dörtgen olduğu için quad kullanıyoruz.
    """
    # Mevcut köşe sayısını başlangıç indeksi olarak al
    i = mesh.Vertices.Count
    # 4 köşeyi mesh'e ekle
    mesh.Vertices.Add(p0.X, p0.Y, p0.Z)
    mesh.Vertices.Add(p1.X, p1.Y, p1.Z)
    mesh.Vertices.Add(p2.X, p2.Y, p2.Z)
    mesh.Vertices.Add(p3.X, p3.Y, p3.Z)
    # Bu 4 köşeyi birleştiren dörtgen yüzey ekle
    mesh.Faces.AddFace(i, i+1, i+2, i+3)

def mesh_e_tri_ekle(mesh, p0, p1, p2):
    """
    3 köşeli bir yüzey (triangle face) ekler.
    Üçgen çatı tepelerinde kullanılır.
    """
    i = mesh.Vertices.Count
    mesh.Vertices.Add(p0.X, p0.Y, p0.Z)
    mesh.Vertices.Add(p1.X, p1.Y, p1.Z)
    mesh.Vertices.Add(p2.X, p2.Y, p2.Z)
    mesh.Faces.AddFace(i, i+1, i+2)

def p3d(x, y, z):
    """Kısa yol: rg.Point3d(x, y, z) oluşturur."""
    return rg.Point3d(x, y, z)

# =============================================================================
# YARDIMCI: OBJ + JSON KAYDETME
# =============================================================================

def obj_olarak_kaydet(mesh, dosya_yolu):
    """
    Rhino Mesh nesnesini .obj formatında kaydeder.

    OBJ formatı çok basit bir 3D dosya formatıdır:
    - 'v' satırları: köşe koordinatları (vertex)
    - 'f' satırları: yüzey tanımları (face) - hangi köşeler birbirine bağlı

    Örnek OBJ dosyası:
        v 0.0 0.0 0.0    ← köşe 1: orijin
        v 5.0 0.0 0.0    ← köşe 2
        v 5.0 0.0 3.0    ← köşe 3
        v 0.0 0.0 3.0    ← köşe 4
        f 1 2 3 4        ← bu 4 köşe bir yüzey oluşturur
    """
    satirlar = ["# Mimari AI - Otomatik Üretilmiş Bina Modeli\n"]

    # Tüm köşeleri yaz
    for i in range(mesh.Vertices.Count):
        v = mesh.Vertices[i]
        satirlar.append("v {:.6f} {:.6f} {:.6f}\n".format(v.X, v.Y, v.Z))

    # Tüm yüzeyleri yaz (OBJ'de indeksler 1'den başlar, Python'da 0'dan)
    for i in range(mesh.Faces.Count):
        f = mesh.Faces[i]
        if f.IsTriangle:
            # Üçgen yüzey
            satirlar.append("f {} {} {}\n".format(f.A+1, f.B+1, f.C+1))
        else:
            # Dörtgen yüzey
            satirlar.append("f {} {} {} {}\n".format(f.A+1, f.B+1, f.C+1, f.D+1))

    with open(dosya_yolu, "w") as f:
        f.writelines(satirlar)

def json_olarak_kaydet(veri, dosya_yolu):
    """
    Sözlük (dict) verisini .json formatında kaydeder.

    JSON formatı: insan okuyabilir veri formatı.
    Örnek:
        {
          "model_id": 42,
          "parametreler": {"genislik": 10.0, ...},
          "yuzey_etiketleri": [0, 0, 1, 4, 4, ...]
        }

    Bu JSON dosyası Faz 2'de hangi yüzeyin hangi sınıfa ait olduğunu gösterir.
    PointNet eğitimi bu etiketleri kullanır.
    """
    with open(dosya_yolu, "w", encoding="utf-8") as f:
        json.dump(veri, f, indent=2, ensure_ascii=False)

# =============================================================================
# BİNA ÜRETME MOTORU
# =============================================================================

class BinaUretici:
    """
    Rastgele parametrik bina modeli üretir.

    Her çağrıda farklı ölçü, kat sayısı, pencere yerleşimi,
    çatı tipi üretir ve hem geometriyi (mesh) hem etiketleri (labels) döndürür.
    """

    def __init__(self, tohum_degeri):
        # Rastgele sayı üreticisini başlat
        # Aynı tohum → aynı sonuçlar (bilimsel tekrarlanabilirlik için önemli)
        self.rng = random.Random(tohum_degeri)

    def rastgele(self, min_deger, max_deger):
        """min ile max arasında rastgele ondalıklı sayı üretir."""
        return self.rng.uniform(min_deger, max_deger)

    def rastgele_int(self, min_deger, max_deger):
        """min ile max arasında rastgele tam sayı üretir."""
        return self.rng.randint(min_deger, max_deger)

    def secim(self, liste):
        """Listeden rastgele bir eleman seçer."""
        return self.rng.choice(liste)

    # -------------------------------------------------------------------------
    # ANA FONKSİYON: Tek bir bina modeli üret
    # -------------------------------------------------------------------------

    def bina_uret(self, model_id):
        """
        model_id: Bu modelin sıra numarası (0-499)

        Döndürür:
            mesh:   Rhino Mesh nesnesi (tüm yüzeyler birleştirilmiş)
            etiket: Liste - her yüzey için sınıf kodu [0,0,1,4,4,5,5,...]
            bilgi:  Sözlük - modelin parametreleri (JSON'a kaydedilecek)
        """

        # --- Bina Parametrelerini Rastgele Seç ---
        genislik    = self.rastgele(6.0, 20.0)     # X yönü (metre)
        derinlik    = self.rastgele(6.0, 20.0)     # Y yönü (metre)
        kat_sayisi  = self.rastgele_int(1, 5)       # Kat adedi
        kat_h       = 3.0                           # Her kat yüksekliği (sabit 3m)
        toplam_h    = kat_sayisi * kat_h            # Toplam bina yüksekliği

        # Bina planı tipi
        plan_tipi   = self.secim(["dikdortgen", "L_sekli", "T_sekli"])

        # Çatı tipi
        cati_tipi   = self.secim(["flat", "pitched", "hip"])
        cati_eğimi  = self.rastgele(20.0, 45.0)    # Derece cinsinden
        sacak_uzu   = 0.5                           # Saçak çıkıntısı (metre)

        # Pencere parametreleri
        pencere_oran = self.rastgele(0.15, 0.45)   # Duvar alanının %15-45'i pencere

        # Kapı parametreleri
        kapi_gen    = 1.0                           # Kapı genişliği (metre)
        kapi_yuk    = 2.1                           # Kapı yüksekliği (metre)

        # --- Mesh ve Etiket Listelerini Hazırla ---
        birlesik_mesh = rg.Mesh()  # Tüm parçaları bu mesh'e ekleyeceğiz
        etiketler     = []         # Her yüzeyin sınıf kodu buraya

        # --- Bina Gövdesini Çiz ---
        # Plan tipine göre farklı footprint (taban izi) kullan
        if plan_tipi == "dikdortgen":
            kitleler = self._dikdortgen_kitle(genislik, derinlik)
        elif plan_tipi == "L_sekli":
            kitleler = self._L_kitle(genislik, derinlik)
        else:  # T_sekli
            kitleler = self._T_kitle(genislik, derinlik)

        # Her kitle için kat kat duvar, döşeme, tavan ekle
        for (kx0, ky0, kx1, ky1) in kitleler:
            self._govde_ekle(
                birlesik_mesh, etiketler,
                kx0, ky0, kx1, ky1,
                toplam_h, kat_sayisi, kat_h,
                pencere_oran, kapi_gen, kapi_yuk
            )

        # --- Çatıyı Çiz ---
        # Tüm kitlerin toplam bounding box'ı üzerine çatı çiz
        tum_x0 = min(k[0] for k in kitleler)
        tum_y0 = min(k[1] for k in kitleler)
        tum_x1 = max(k[2] for k in kitleler)
        tum_y1 = max(k[3] for k in kitleler)

        if cati_tipi == "flat":
            self._duz_cati_ekle(
                birlesik_mesh, etiketler,
                tum_x0, tum_y0, tum_x1, tum_y1, toplam_h, sacak_uzu
            )
        elif cati_tipi == "pitched":
            self._beşik_cati_ekle(
                birlesik_mesh, etiketler,
                tum_x0, tum_y0, tum_x1, tum_y1, toplam_h, cati_eğimi, sacak_uzu
            )
        else:  # hip
            self._kırma_cati_ekle(
                birlesik_mesh, etiketler,
                tum_x0, tum_y0, tum_x1, tum_y1, toplam_h, cati_eğimi, sacak_uzu
            )

        # Normalleri hesapla (ışık ve görüntüleme için gerekli)
        birlesik_mesh.Normals.ComputeNormals()
        birlesik_mesh.Compact()

        # Modelin tüm parametrelerini kayıt için topla
        bilgi = {
            "model_id":      model_id,
            "plan_tipi":     plan_tipi,
            "cati_tipi":     cati_tipi,
            "genislik":      round(genislik, 3),
            "derinlik":      round(derinlik, 3),
            "kat_sayisi":    kat_sayisi,
            "kat_yuksekligi": kat_h,
            "toplam_yukseklik": round(toplam_h, 3),
            "pencere_orani": round(pencere_oran, 3),
            "cati_egimi_derece": round(cati_eğimi, 1),
            "sacak_uzunlugu": sacak_uzu,
            "yuzey_sayisi":  birlesik_mesh.Faces.Count,
            "etiket_listesi": etiketler,
            "sinif_aciklamasi": {
                "0": "wall",    "1": "floor", "2": "ceiling",
                "3": "door",    "4": "window","5": "roof", "6": "eave"
            }
        }

        return birlesik_mesh, etiketler, bilgi

    # -------------------------------------------------------------------------
    # PLAN TİPLERİ
    # Her fonksiyon (x0,y0,x1,y1) tuple listesi döndürür.
    # Her tuple = bir dikdörtgen blok/kitle tanımlar.
    # -------------------------------------------------------------------------

    def _dikdortgen_kitle(self, genislik, derinlik):
        """Tek dikdörtgen plan - en basit bina tipi."""
        return [(0.0, 0.0, genislik, derinlik)]

    def _L_kitle(self, genislik, derinlik):
        """
        L şeklinde plan - iki bloktan oluşur.

        [BLOK1]
        [BLOK1][BLOK2]

        """
        # Birinci blok: tam yükseklik, yarım genişlik
        b1x1 = genislik * 0.6   # Birinci bloğun x uzunluğu
        b1y1 = derinlik         # Birinci bloğun y uzunluğu

        # İkinci blok: yarım yükseklik
        b2x0 = 0.0
        b2x1 = genislik
        b2y0 = 0.0
        b2y1 = derinlik * 0.6

        return [
            (0.0,  0.0,  b1x1, b1y1),   # Dikey kol
            (b2x0, b2y0, b2x1, b2y1),   # Yatay kol
        ]

    def _T_kitle(self, genislik, derinlik):
        """
        T şeklinde plan - üç bloktan oluşur.

           [ÜST]
        [SOL][ORTA][SAĞ]

        """
        ort_gen = genislik * 0.4          # Orta kol genişliği
        ort_x0  = genislik * 0.3          # Orta kolun başlangıcı

        return [
            (0.0,   0.0,           genislik,          derinlik * 0.5),   # Yatay bar
            (ort_x0, derinlik*0.5, ort_x0 + ort_gen,  derinlik),         # Dikey kol
        ]

    # -------------------------------------------------------------------------
    # GOVDE: Duvarlar, Pencereler, Kapılar, Döşemeler
    # -------------------------------------------------------------------------

    def _govde_ekle(self, mesh, etiketler,
                    x0, y0, x1, y1,
                    toplam_h, kat_sayisi, kat_h,
                    pencere_oran, kapi_gen, kapi_yuk):
        """
        Bir dikdörtgen kitleye kat kat bina elemanları ekler.

        x0,y0,x1,y1: Planın köşe koordinatları
        toplam_h:     Binanın toplam yüksekliği
        kat_sayisi:   Kat sayısı
        kat_h:        Tek kat yüksekliği
        pencere_oran: Pencere/duvar alan oranı
        kapi_gen/yuk: Kapı boyutları
        """
        genislik = x1 - x0
        derinlik = y1 - y0

        # 4 dış duvar yüzeyinin tanımı: başlangıç noktası + yön vektörü + uzunluk
        # (baslangic_x, baslangic_y, bitis_x, bitis_y, normal_yonu)
        duvarlar = [
            (x0, y0, x1, y0, "gney"),   # Güney duvarı (ön cephe)
            (x1, y0, x1, y1, "dogu"),   # Doğu duvarı
            (x1, y1, x0, y1, "kzey"),   # Kuzey duvarı (arka cephe)
            (x0, y1, x0, y0, "bati"),   # Batı duvarı
        ]

        # Hangi duvarda kapı olacak? (Sadece güney/ön cephede)
        kapi_duvar = "gney"

        for (dx0, dy0, dx1, dy1, yon) in duvarlar:
            duvar_uzunlugu = math.sqrt((dx1-dx0)**2 + (dy1-dy0)**2)

            # --- DÖŞEMELER ve TAVANLAR (kat aralarına) ---
            for kat in range(kat_sayisi):
                z_alt = kat * kat_h
                z_ust = (kat + 1) * kat_h

                # Sadece ilk duvar döngüsünde döşeme/tavan ekle (tekrar etmesin)
                if yon == "gney":
                    # Döşeme (zeminden 0 yükseklikte, kat=0 için)
                    # ya da ara kat döşemesi
                    zer = z_alt
                    mesh_e_quad_ekle(mesh,
                        p3d(x0, y0, zer), p3d(x1, y0, zer),
                        p3d(x1, y1, zer), p3d(x0, y1, zer)
                    )
                    etiketler.append(SINIF["floor"])

                    # Tavan (son katta çatı olduğu için tavan yok, o yüzey "ceiling")
                    if kat < kat_sayisi - 1:
                        mesh_e_quad_ekle(mesh,
                            p3d(x0, y0, z_ust), p3d(x1, y0, z_ust),
                            p3d(x1, y1, z_ust), p3d(x0, y1, z_ust)
                        )
                        etiketler.append(SINIF["ceiling"])

            # --- KAT KAT DUVARLARI ÇIZDIR ---
            for kat in range(kat_sayisi):
                z_alt = kat * kat_h
                z_ust = (kat + 1) * kat_h

                # Bu katta pencere var mı ve nerede?
                pencere_sayisi = max(1, int(pencere_oran * duvar_uzunlugu))

                # Duvarı parçalara böl: boşluksuz duvar panelleri
                # Bölme mantığı: duvar uzunluğunu eşit parçalara böl
                # Her parçada ya pencere ya düz duvar olsun
                self._duvar_parcalari_ekle(
                    mesh, etiketler,
                    dx0, dy0, dx1, dy1,
                    z_alt, z_ust,
                    duvar_uzunlugu, pencere_sayisi,
                    kapi_gen, kapi_yuk,
                    kat, yon == kapi_duvar
                )

    def _duvar_parcalari_ekle(self, mesh, etiketler,
                               dx0, dy0, dx1, dy1,
                               z_alt, z_ust,
                               duvar_uzunlugu, pencere_sayisi,
                               kapi_gen, kapi_yuk,
                               kat_no, kapi_var_mi):
        """
        Bir duvar yüzeyini pencereli/kapılı bölümlere ayırır ve ekler.

        Duvar bölünme mantığı (soldan sağa):
        |boşluk|Pencere|boşluk|Pencere|boşluk|

        dx0,dy0 → dx1,dy1 : Duvarın başlangıç ve bitiş yatay koordinatları
        z_alt, z_ust       : Kat yükseklikleri
        pencere_sayisi     : Bu katta kaç pencere olacak
        kapi_var_mi        : Zemin katta ön cephede kapı eklenecek mi
        """
        kat_yuk = z_ust - z_alt

        # Yatay birim vektör (duvar boyunca)
        dx = dx1 - dx0
        dy = dy1 - dy0
        uzunluk = math.sqrt(dx*dx + dy*dy)
        if uzunluk < 0.001:
            return  # Sıfır uzunluklu duvar, atla
        ux = dx / uzunluk  # x birim vektörü
        uy = dy / uzunluk  # y birim vektörü

        # Pencere boyutları
        pen_gen = 1.2    # Pencere genişliği (metre)
        pen_yuk = 1.2    # Pencere yüksekliği (metre)
        pen_alt = z_alt + 0.9   # Pencere deniz seviyesinden yüksekliği
        pen_ust = pen_alt + pen_yuk

        # Sığmıyorsa pencere ekleme
        if pen_ust > z_ust - 0.1:
            pen_sayisi = 0
        else:
            pen_sayisi = pencere_sayisi

        # Kapı sadece zemin katta ve ön cephede
        kapi_bu_katta = (kapi_var_mi and kat_no == 0)

        # Duvarı segmentlere böl
        # Kapı için merkeze yakın konum ayarla
        segmentler = []  # (baslangic_t, bitis_t, tip) → t: 0..1 arası konum

        if kapi_bu_katta and uzunluk >= (kapi_gen + 1.0):
            # Kapıyı ortaya koy
            kapi_baslangic = (uzunluk - kapi_gen) / 2.0
            kapi_bitis     = kapi_baslangic + kapi_gen

            # Kapı öncesi duvar
            segmentler.append((0.0, kapi_baslangic, "wall"))
            # Kapı
            segmentler.append((kapi_baslangic, kapi_bitis, "door"))
            # Kapı sonrası duvar
            segmentler.append((kapi_bitis, uzunluk, "wall"))
        else:
            segmentler.append((0.0, uzunluk, "wall"))

        # Şimdi her segmenti çiz
        for (seg_bas, seg_bit, seg_tip) in segmentler:
            seg_uzunluk = seg_bit - seg_bas

            if seg_tip == "door":
                # Kapı bölümü: 3 parça (sol duvar şeridi, kapı boşluğu, sağ duvar şeridi)
                # Kapının üstü: kapi_yuk'tan z_ust'a
                kapi_alt_z = z_alt
                kapi_ust_z = z_alt + kapi_yuk

                # Kapının kendisi (çerçeveli boşluk yerine renkli mesh)
                p0 = p3d(dx0 + ux*seg_bas,  dy0 + uy*seg_bas,  kapi_alt_z)
                p1 = p3d(dx0 + ux*seg_bit,  dy0 + uy*seg_bit,  kapi_alt_z)
                p2 = p3d(dx0 + ux*seg_bit,  dy0 + uy*seg_bit,  kapi_ust_z)
                p3_ = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas,  kapi_ust_z)
                mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                etiketler.append(SINIF["door"])

                # Kapı üstü duvar şeridi
                if kapi_ust_z < z_ust:
                    p0 = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, kapi_ust_z)
                    p1 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, kapi_ust_z)
                    p2 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, z_ust)
                    p3_ = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, z_ust)
                    mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                    etiketler.append(SINIF["wall"])

            elif seg_tip == "wall" and pen_sayisi > 0 and seg_uzunluk >= (pen_gen + 0.5):
                # Duvar bölümüne pencere(ler) ekle
                # Pencereleri eşit aralıklarla dağıt
                aralik = seg_uzunluk / pen_sayisi

                for p_i in range(pen_sayisi):
                    # Bu pencerenin yatay konumu (segment içinde)
                    p_merkez = seg_bas + aralik * p_i + aralik * 0.5
                    p_sol    = p_merkez - pen_gen / 2.0
                    p_sag    = p_merkez + pen_gen / 2.0

                    # Sınır kontrolü
                    if p_sol < seg_bas + 0.2 or p_sag > seg_bit - 0.2:
                        continue  # Sığmıyor, atla

                    # --- Sol duvar şeridi ---
                    if p_sol > seg_bas:
                        p0 = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, z_alt)
                        p1 = p3d(dx0 + ux*p_sol,   dy0 + uy*p_sol,   z_alt)
                        p2 = p3d(dx0 + ux*p_sol,   dy0 + uy*p_sol,   z_ust)
                        p3_ = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, z_ust)
                        mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                        etiketler.append(SINIF["wall"])

                    # --- Pencere altı duvar şeridi ---
                    if pen_alt > z_alt:
                        p0 = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, z_alt)
                        p1 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, z_alt)
                        p2 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, pen_alt)
                        p3_ = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, pen_alt)
                        mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                        etiketler.append(SINIF["wall"])

                    # --- Pencere ---
                    p0 = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, pen_alt)
                    p1 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, pen_alt)
                    p2 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, pen_ust)
                    p3_ = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, pen_ust)
                    mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                    etiketler.append(SINIF["window"])

                    # --- Pencere üstü duvar şeridi ---
                    if pen_ust < z_ust:
                        p0 = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, pen_ust)
                        p1 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, pen_ust)
                        p2 = p3d(dx0 + ux*p_sag, dy0 + uy*p_sag, z_ust)
                        p3_ = p3d(dx0 + ux*p_sol, dy0 + uy*p_sol, z_ust)
                        mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                        etiketler.append(SINIF["wall"])

                    # --- Sağ duvar şeridi (son pencereden sonra) ---
                    if p_i == pen_sayisi - 1 and p_sag < seg_bit:
                        p0 = p3d(dx0 + ux*p_sag,  dy0 + uy*p_sag,  z_alt)
                        p1 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, z_alt)
                        p2 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, z_ust)
                        p3_ = p3d(dx0 + ux*p_sag,  dy0 + uy*p_sag,  z_ust)
                        mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                        etiketler.append(SINIF["wall"])

            else:
                # Pencere yok, düz duvar
                p0 = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, z_alt)
                p1 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, z_alt)
                p2 = p3d(dx0 + ux*seg_bit, dy0 + uy*seg_bit, z_ust)
                p3_ = p3d(dx0 + ux*seg_bas, dy0 + uy*seg_bas, z_ust)
                mesh_e_quad_ekle(mesh, p0, p1, p2, p3_)
                etiketler.append(SINIF["wall"])

    # -------------------------------------------------------------------------
    # ÇATI TİPLERİ
    # -------------------------------------------------------------------------

    def _duz_cati_ekle(self, mesh, etiketler,
                        x0, y0, x1, y1, z_tavan, sacak):
        """
        Düz çatı ekler. Modern binalar için.

        Sadece tek bir yatay yüzey. Saçak çıkıntısı dışarı taşar.

             ___________
            |  ÇATI    |   ← Saçak çıkıntısı (sacak kadar dışa taşmış)
        [   BINA   ]
        """
        # Saçak çıkıntısı eklenmiş koordinatlar
        rx0 = x0 - sacak
        ry0 = y0 - sacak
        rx1 = x1 + sacak
        ry1 = y1 + sacak

        # Düz çatı yüzeyi
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry0, z_tavan),
            p3d(rx1, ry0, z_tavan),
            p3d(rx1, ry1, z_tavan),
            p3d(rx0, ry1, z_tavan)
        )
        etiketler.append(SINIF["roof"])

        # Saçak yüzeyleri (4 kenarda aşağıya sarkma)
        sacak_alt = z_tavan - 0.2   # Saçak kalınlığı

        # Ön saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry0, sacak_alt), p3d(rx1, ry0, sacak_alt),
            p3d(rx1, ry0, z_tavan),   p3d(rx0, ry0, z_tavan)
        )
        etiketler.append(SINIF["eave"])

        # Arka saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry1, z_tavan), p3d(rx1, ry1, z_tavan),
            p3d(rx1, ry1, sacak_alt), p3d(rx0, ry1, sacak_alt)
        )
        etiketler.append(SINIF["eave"])

        # Sağ saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx1, ry0, sacak_alt), p3d(rx1, ry1, sacak_alt),
            p3d(rx1, ry1, z_tavan),   p3d(rx1, ry0, z_tavan)
        )
        etiketler.append(SINIF["eave"])

        # Sol saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry0, z_tavan), p3d(rx0, ry1, z_tavan),
            p3d(rx0, ry1, sacak_alt), p3d(rx0, ry0, sacak_alt)
        )
        etiketler.append(SINIF["eave"])

    def _besik_cati_ekle(self, mesh, etiketler,
                          x0, y0, x1, y1, z_tavan, egim_derece, sacak):
        """
        Beşik çatı (pitched/gable roof) ekler.

        Geleneksel çatı tipi - iki eğimli yüzey + iki alın üçgeni.
        Çatı mahyası (ridge) ortada uzanır.

              /\\         ← Mahya (tepe çizgisi)
             /  \\
            /    \\
           / ÇATI \\
          /________\\
          [  BİNA  ]
        """
        # Saçak ile genişletilmiş koordinatlar
        rx0 = x0 - sacak
        ry0 = y0 - sacak
        rx1 = x1 + sacak
        ry1 = y1 + sacak

        gen = rx1 - rx0   # Genişlik (X yönü)
        dep = ry1 - ry0   # Derinlik (Y yönü)

        # Çatı yüksekliği: eğim açısından hesapla
        # tan(egim) = yükseklik / (yarı derinlik)
        egim_rad   = math.radians(egim_derece)
        cati_yukse = math.tan(egim_rad) * (dep / 2.0)

        # Mahya yüksekliği (zeminden)
        z_mahya = z_tavan + cati_yukse

        # Mahya çizgisi orta Y'de, tüm X boyunca uzanır
        mahya_y = (ry0 + ry1) / 2.0

        # Ön çatı yüzeyi (güney tarafa bakan eğimli yüzey)
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry0, z_tavan),   # Sol-ön-alt
            p3d(rx1, ry0, z_tavan),   # Sağ-ön-alt
            p3d(rx1, mahya_y, z_mahya), # Sağ-mahya
            p3d(rx0, mahya_y, z_mahya)  # Sol-mahya
        )
        etiketler.append(SINIF["roof"])

        # Arka çatı yüzeyi (kuzey tarafa bakan eğimli yüzey)
        mesh_e_quad_ekle(mesh,
            p3d(rx0, mahya_y, z_mahya),  # Sol-mahya
            p3d(rx1, mahya_y, z_mahya),  # Sağ-mahya
            p3d(rx1, ry1, z_tavan),      # Sağ-arka-alt
            p3d(rx0, ry1, z_tavan)       # Sol-arka-alt
        )
        etiketler.append(SINIF["roof"])

        # Sol alın üçgeni (bati alın)
        mesh_e_tri_ekle(mesh,
            p3d(rx0, ry0, z_tavan),
            p3d(rx0, ry1, z_tavan),
            p3d(rx0, mahya_y, z_mahya)
        )
        etiketler.append(SINIF["roof"])

        # Sağ alın üçgeni (dogu alın)
        mesh_e_tri_ekle(mesh,
            p3d(rx1, ry0, z_tavan),
            p3d(rx1, mahya_y, z_mahya),
            p3d(rx1, ry1, z_tavan)
        )
        etiketler.append(SINIF["roof"])

        # Saçak yüzeyleri (ön ve arka kenarlarda)
        sacak_alt = z_tavan - 0.2

        # Ön saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry0, sacak_alt), p3d(rx1, ry0, sacak_alt),
            p3d(rx1, ry0, z_tavan),   p3d(rx0, ry0, z_tavan)
        )
        etiketler.append(SINIF["eave"])

        # Arka saçak
        mesh_e_quad_ekle(mesh,
            p3d(rx0, ry1, z_tavan), p3d(rx1, ry1, z_tavan),
            p3d(rx1, ry1, sacak_alt), p3d(rx0, ry1, sacak_alt)
        )
        etiketler.append(SINIF["eave"])

    def _kirma_cati_ekle(self, mesh, etiketler,
                          x0, y0, x1, y1, z_tavan, egim_derece, sacak):
        """
        Kırma çatı (hip roof) ekler.

        Dört tarafta da eğimli yüzey var, alın üçgeni yok.
        Geleneksel Türk evlerinde sık görülen çatı tipi.

               /\\
              /  \\
             / /\\ \\
            / /  \\ \\
           /_/ ÇATI \\_\\
        """
        rx0 = x0 - sacak
        ry0 = y0 - sacak
        rx1 = x1 + sacak
        ry1 = y1 + sacak

        gen = rx1 - rx0
        dep = ry1 - ry0

        # Kırma çatıda hem X hem Y tarafından eğim var
        # Küçük boyut çatı yüksekliğini belirler
        min_boyut    = min(gen, dep)
        egim_rad     = math.radians(egim_derece)
        cati_yukse   = math.tan(egim_rad) * (min_boyut / 2.0)

        z_mahya      = z_tavan + cati_yukse

        merkez_x     = (rx0 + rx1) / 2.0
        merkez_y     = (ry0 + ry1) / 2.0

        # Kırma çatı: 4 üçgen/dörtgen yüzey
        # Tüm boyutlar eşit ise 4 üçgen, değilse ön/arka dörtgen, yanlar üçgen

        if abs(gen - dep) < 0.5:
            # Kare plan → 4 üçgen yüzey

            # Ön (güney) üçgen
            mesh_e_tri_ekle(mesh,
                p3d(rx0, ry0, z_tavan),
                p3d(rx1, ry0, z_tavan),
                p3d(merkez_x, merkez_y, z_mahya)
            )
            etiketler.append(SINIF["roof"])

            # Arka (kuzey) üçgen
            mesh_e_tri_ekle(mesh,
                p3d(rx1, ry1, z_tavan),
                p3d(rx0, ry1, z_tavan),
                p3d(merkez_x, merkez_y, z_mahya)
            )
            etiketler.append(SINIF["roof"])

            # Sağ (doğu) üçgen
            mesh_e_tri_ekle(mesh,
                p3d(rx1, ry0, z_tavan),
                p3d(rx1, ry1, z_tavan),
                p3d(merkez_x, merkez_y, z_mahya)
            )
            etiketler.append(SINIF["roof"])

            # Sol (batı) üçgen
            mesh_e_tri_ekle(mesh,
                p3d(rx0, ry1, z_tavan),
                p3d(rx0, ry0, z_tavan),
                p3d(merkez_x, merkez_y, z_mahya)
            )
            etiketler.append(SINIF["roof"])

        else:
            # Dikdörtgen plan → uzun kenarlar dörtgen, kısa kenarlar üçgen

            if gen > dep:
                # Yatay (X) boyut büyük → mahya X boyunca uzanır
                mahya_x0 = rx0 + (dep / 2.0)
                mahya_x1 = rx1 - (dep / 2.0)

                # Ön dörtgen
                mesh_e_quad_ekle(mesh,
                    p3d(rx0,    ry0, z_tavan),
                    p3d(rx1,    ry0, z_tavan),
                    p3d(mahya_x1, merkez_y, z_mahya),
                    p3d(mahya_x0, merkez_y, z_mahya)
                )
                etiketler.append(SINIF["roof"])

                # Arka dörtgen
                mesh_e_quad_ekle(mesh,
                    p3d(mahya_x0, merkez_y, z_mahya),
                    p3d(mahya_x1, merkez_y, z_mahya),
                    p3d(rx1, ry1, z_tavan),
                    p3d(rx0, ry1, z_tavan)
                )
                etiketler.append(SINIF["roof"])

                # Sol üçgen
                mesh_e_tri_ekle(mesh,
                    p3d(rx0, ry0, z_tavan),
                    p3d(mahya_x0, merkez_y, z_mahya),
                    p3d(rx0, ry1, z_tavan)
                )
                etiketler.append(SINIF["roof"])

                # Sağ üçgen
                mesh_e_tri_ekle(mesh,
                    p3d(rx1, ry0, z_tavan),
                    p3d(rx1, ry1, z_tavan),
                    p3d(mahya_x1, merkez_y, z_mahya)
                )
                etiketler.append(SINIF["roof"])

            else:
                # Dikey (Y) boyut büyük
                mahya_y0 = ry0 + (gen / 2.0)
                mahya_y1 = ry1 - (gen / 2.0)

                # Sol dörtgen
                mesh_e_quad_ekle(mesh,
                    p3d(rx0, ry0, z_tavan),
                    p3d(merkez_x, mahya_y0, z_mahya),
                    p3d(merkez_x, mahya_y1, z_mahya),
                    p3d(rx0, ry1, z_tavan)
                )
                etiketler.append(SINIF["roof"])

                # Sağ dörtgen
                mesh_e_quad_ekle(mesh,
                    p3d(merkez_x, mahya_y0, z_mahya),
                    p3d(rx1, ry0, z_tavan),
                    p3d(rx1, ry1, z_tavan),
                    p3d(merkez_x, mahya_y1, z_mahya)
                )
                etiketler.append(SINIF["roof"])

                # Ön üçgen
                mesh_e_tri_ekle(mesh,
                    p3d(rx0, ry0, z_tavan),
                    p3d(rx1, ry0, z_tavan),
                    p3d(merkez_x, mahya_y0, z_mahya)
                )
                etiketler.append(SINIF["roof"])

                # Arka üçgen
                mesh_e_tri_ekle(mesh,
                    p3d(rx0, ry1, z_tavan),
                    p3d(merkez_x, mahya_y1, z_mahya),
                    p3d(rx1, ry1, z_tavan)
                )
                etiketler.append(SINIF["roof"])

        # Saçak yüzeyleri (4 kenar)
        sacak_alt = z_tavan - 0.2

        for (sx0, sy0, sx1, sy1) in [
            (rx0, ry0, rx1, ry0),   # Ön
            (rx0, ry1, rx1, ry1),   # Arka
            (rx1, ry0, rx1, ry1),   # Sağ
            (rx0, ry0, rx0, ry1),   # Sol
        ]:
            mesh_e_quad_ekle(mesh,
                p3d(sx0, sy0, sacak_alt), p3d(sx1, sy1, sacak_alt),
                p3d(sx1, sy1, z_tavan),   p3d(sx0, sy0, z_tavan)
            )
            etiketler.append(SINIF["eave"])

# =============================================================================
# ANA ÇALIŞTIRMA BLOĞU
# Grasshopper bu bloğu "Run" butonuna basınca çalıştırır.
# =============================================================================

def ana_uretim():
    """
    500 bina modeli üretir ve kaydeder.
    Her 50 modelde bir ilerleme mesajı yazdırır.
    """

    # Çıktı klasörlerini oluştur (yoksa)
    for klasor in [OBJ_KLASORU, JSON_KLASORU]:
        if not os.path.exists(klasor):
            os.makedirs(klasor)
            print("Klasor olusturuldu: {}".format(klasor))

    uretici = BinaUretici(TOHUM)

    basarili = 0
    hatali   = 0

    print("=" * 60)
    print("  BINA MODELI URETIMI BASLIYOR")
    print("  Toplam: {} model".format(MODEL_SAYISI))
    print("  Cikti:  {}".format(OBJ_KLASORU))
    print("=" * 60)

    for i in range(MODEL_SAYISI):
        try:
            # Bina üret
            mesh, etiketler, bilgi = uretici.bina_uret(i)

            # Dosya adları
            obj_dosya  = os.path.join(OBJ_KLASORU,  "bina_{:04d}.obj".format(i))
            json_dosya = os.path.join(JSON_KLASORU, "bina_{:04d}.json".format(i))

            # Kaydet
            obj_olarak_kaydet(mesh, obj_dosya)
            json_olarak_kaydet(bilgi, json_dosya)

            basarili += 1

            # Her 50 modelde ilerleme göster
            if (i + 1) % 50 == 0:
                print("  [{}/{}] {} model uretildi...".format(
                    i+1, MODEL_SAYISI, basarili))

        except Exception as e:
            hatali += 1
            print("  HATA - Model {}: {}".format(i, str(e)))

    print()
    print("=" * 60)
    print("  URETIM TAMAMLANDI!")
    print("  Basarili: {}".format(basarili))
    print("  Hatali:   {}".format(hatali))
    print("  OBJ:  {}".format(OBJ_KLASORU))
    print("  JSON: {}".format(JSON_KLASORU))
    print("=" * 60)

    return basarili


# Grasshopper'da script bu satırla çalışır
if __name__ == "__main__":
    ana_uretim()
else:
    # Grasshopper Python bileşeni için doğrudan çalıştır
    ana_uretim()

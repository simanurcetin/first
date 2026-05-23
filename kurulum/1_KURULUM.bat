@echo off
chcp 65001 >nul
echo ============================================================
echo   MİMARİ AI PROJESİ - KURULUM
echo ============================================================
echo.
echo Bu işlem 5-10 dakika sürebilir, lütfen bekleyin...
echo.

REM Conda'nın kurulu olup olmadığını kontrol et
where conda >nul 2>&1
if errorlevel 1 (
    echo HATA: Conda bulunamadı!
    echo Lütfen önce Anaconda veya Miniconda kurun:
    echo https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

echo [1/3] Eski ortam varsa siliniyor...
conda env remove -n mimari_ai -y 2>nul

echo.
echo [2/3] Yeni conda ortamı kuruluyor (mimari_ai)...
cd /d "%~dp0.."
conda env create -f environment.yml
if errorlevel 1 (
    echo.
    echo HATA: Ortam kurulumu başarısız!
    pause
    exit /b 1
)

echo.
echo [3/3] Klasör yapısı oluşturuluyor...
mkdir data\obj_files  2>nul
mkdir data\json_files 2>nul
mkdir data\processed  2>nul

echo.
echo ============================================================
echo   KURULUM TAMAMLANDI!
echo   Şimdi 2_ORTAMI_TEST_ET.bat dosyasını çalıştırın.
echo ============================================================
pause

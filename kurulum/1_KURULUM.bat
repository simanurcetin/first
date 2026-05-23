@echo off
chcp 65001 >nul
title Mimari AI - Kurulum

echo ============================================================
echo   MIMARI AI PROJESI - KURULUM
echo ============================================================
echo.
echo Bu islem 10-20 dakika surebilir (internet hizina gore).
echo Pencereyi kapatmayin!
echo.

REM ============================================================
REM ADIM 1: Conda'yi bul
REM (Cift tiklamada conda PATH'te olmaz, elle bulmak gerekir)
REM ============================================================
echo [1/5] Conda aranıyor...
set CONDA_ROOT=

if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat"      set CONDA_ROOT=%USERPROFILE%\anaconda3&       goto :conda_bulundu
if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat"      set CONDA_ROOT=%USERPROFILE%\Anaconda3&       goto :conda_bulundu
if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat"     set CONDA_ROOT=%USERPROFILE%\miniconda3&      goto :conda_bulundu
if exist "%USERPROFILE%\Miniconda3\Scripts\activate.bat"     set CONDA_ROOT=%USERPROFILE%\Miniconda3&      goto :conda_bulundu
if exist "%LOCALAPPDATA%\anaconda3\Scripts\activate.bat"     set CONDA_ROOT=%LOCALAPPDATA%\anaconda3&      goto :conda_bulundu
if exist "%LOCALAPPDATA%\Anaconda3\Scripts\activate.bat"     set CONDA_ROOT=%LOCALAPPDATA%\Anaconda3&      goto :conda_bulundu
if exist "%LOCALAPPDATA%\miniconda3\Scripts\activate.bat"    set CONDA_ROOT=%LOCALAPPDATA%\miniconda3&     goto :conda_bulundu
if exist "%LOCALAPPDATA%\Miniconda3\Scripts\activate.bat"    set CONDA_ROOT=%LOCALAPPDATA%\Miniconda3&     goto :conda_bulundu
if exist "C:\anaconda3\Scripts\activate.bat"                 set CONDA_ROOT=C:\anaconda3&                  goto :conda_bulundu
if exist "C:\Anaconda3\Scripts\activate.bat"                 set CONDA_ROOT=C:\Anaconda3&                  goto :conda_bulundu
if exist "C:\miniconda3\Scripts\activate.bat"                set CONDA_ROOT=C:\miniconda3&                 goto :conda_bulundu
if exist "C:\Miniconda3\Scripts\activate.bat"                set CONDA_ROOT=C:\Miniconda3&                 goto :conda_bulundu
if exist "C:\ProgramData\anaconda3\Scripts\activate.bat"     set CONDA_ROOT=C:\ProgramData\anaconda3&      goto :conda_bulundu
if exist "C:\ProgramData\Anaconda3\Scripts\activate.bat"     set CONDA_ROOT=C:\ProgramData\Anaconda3&      goto :conda_bulundu
if exist "C:\ProgramData\miniconda3\Scripts\activate.bat"    set CONDA_ROOT=C:\ProgramData\miniconda3&     goto :conda_bulundu
if exist "C:\ProgramData\Miniconda3\Scripts\activate.bat"    set CONDA_ROOT=C:\ProgramData\Miniconda3&     goto :conda_bulundu

echo.
echo  *** HATA: Conda bulunamadi! ***
echo.
echo  Cozum: Asagidaki adresten Miniconda indirip kurun:
echo  https://docs.conda.io/en/latest/miniconda.html
echo.
echo  Kurulumda "Add to PATH" secenegini ISARETLEYIN.
echo  Kurulum bittikten sonra bilgisayari yeniden baslatip
echo  bu bat dosyasina tekrar cift tiklayin.
echo.
pause
exit /b 1

:conda_bulundu
echo   Conda bulundu: %CONDA_ROOT%
call "%CONDA_ROOT%\Scripts\activate.bat" "%CONDA_ROOT%"
if errorlevel 1 (
    echo HATA: Conda baslatılamadi!
    pause
    exit /b 1
)

REM ============================================================
REM ADIM 2: Eski ortami temizle
REM ============================================================
echo.
echo [2/5] Eski ortam temizleniyor (varsa)...
call conda deactivate 2>nul
call conda env remove -n mimari_ai --yes 2>nul
echo   Tamam.

REM ============================================================
REM ADIM 3: Python 3.9 ortami olustur
REM ============================================================
echo.
echo [3/5] Python 3.9 ortami olusturuluyor...
call conda create -n mimari_ai python=3.9 --yes
if errorlevel 1 (
    echo.
    echo  *** HATA: Python ortami olusturulamadi! ***
    echo  Internet baglantinizi kontrol edin ve tekrar deneyin.
    pause
    exit /b 1
)
echo   Tamam.

REM ============================================================
REM ADIM 4: Kutuphaneleri kur (pip ile, adim adim)
REM conda run kullaniyoruz - conda activate'e gerek yok
REM ============================================================
echo.
echo [4/5] Kutuphaneler kuruluyor...
echo   (Bu adim 10-15 dakika surebilir, bekleyin)
echo.

echo   --- numpy, pandas, matplotlib, tqdm, scikit-learn ---
call conda run -n mimari_ai pip install numpy==1.24.3 pandas==2.0.3 matplotlib==3.7.2 tqdm==4.65.0 scikit-learn==1.3.0
if errorlevel 1 (
    echo  UYARI: Bazı temel kutuphaneler kurulamadi, devam ediliyor...
)

echo   --- trimesh (3D mesh isleme) ---
call conda run -n mimari_ai pip install trimesh==3.23.5
if errorlevel 1 (
    echo  UYARI: trimesh kurulamadi, tekrar deneniyor...
    call conda run -n mimari_ai pip install trimesh
)

echo   --- open3d (nokta bulutu) ---
call conda run -n mimari_ai pip install open3d==0.17.0
if errorlevel 1 (
    echo  UYARI: open3d 0.17.0 kurulamadi, guncel surumu deneniyor...
    call conda run -n mimari_ai pip install open3d
)

echo   --- PyTorch (derin ogrenme - CPU surumu) ---
call conda run -n mimari_ai pip install torch==2.0.1 torchvision==0.15.2 --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 (
    echo  UYARI: PyTorch indirilemedi, standart surumu deneniyor...
    call conda run -n mimari_ai pip install torch torchvision
)

echo.
echo   Kutuphaneler kuruldu.

REM ============================================================
REM ADIM 5: Klasor yapisi
REM ============================================================
echo.
echo [5/5] Klasor yapisi olusturuluyor...
cd /d "%~dp0.."
if not exist "data"            mkdir data
if not exist "data\obj_files"  mkdir data\obj_files
if not exist "data\json_files" mkdir data\json_files
if not exist "data\processed"  mkdir data\processed
echo   Tamam.

echo.
echo ============================================================
echo   KURULUM TAMAMLANDI!
echo.
echo   Simdi 2_ORTAMI_TEST_ET.bat dosyasina cift tiklayin.
echo ============================================================
echo.
pause

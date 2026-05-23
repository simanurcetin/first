@echo off
chcp 65001 >nul
echo ============================================================
echo   MİMARİ AI - ORTAM TESTİ
echo ============================================================
echo.
cd /d "%~dp0.."
call conda activate mimari_ai
python kurulum/test_ortam.py
echo.
pause

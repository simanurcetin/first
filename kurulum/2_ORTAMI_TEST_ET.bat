@echo off
chcp 65001 >nul
title Mimari AI - Ortam Testi

echo ============================================================
echo   MIMARI AI - ORTAM TESTI
echo ============================================================
echo.

REM Conda'yi bul
set CONDA_ROOT=

if exist "%USERPROFILE%\anaconda3\Scripts\activate.bat"      set CONDA_ROOT=%USERPROFILE%\anaconda3&       goto :conda_ok
if exist "%USERPROFILE%\Anaconda3\Scripts\activate.bat"      set CONDA_ROOT=%USERPROFILE%\Anaconda3&       goto :conda_ok
if exist "%USERPROFILE%\miniconda3\Scripts\activate.bat"     set CONDA_ROOT=%USERPROFILE%\miniconda3&      goto :conda_ok
if exist "%USERPROFILE%\Miniconda3\Scripts\activate.bat"     set CONDA_ROOT=%USERPROFILE%\Miniconda3&      goto :conda_ok
if exist "%LOCALAPPDATA%\anaconda3\Scripts\activate.bat"     set CONDA_ROOT=%LOCALAPPDATA%\anaconda3&      goto :conda_ok
if exist "%LOCALAPPDATA%\Anaconda3\Scripts\activate.bat"     set CONDA_ROOT=%LOCALAPPDATA%\Anaconda3&      goto :conda_ok
if exist "%LOCALAPPDATA%\miniconda3\Scripts\activate.bat"    set CONDA_ROOT=%LOCALAPPDATA%\miniconda3&     goto :conda_ok
if exist "%LOCALAPPDATA%\Miniconda3\Scripts\activate.bat"    set CONDA_ROOT=%LOCALAPPDATA%\Miniconda3&     goto :conda_ok
if exist "C:\anaconda3\Scripts\activate.bat"                 set CONDA_ROOT=C:\anaconda3&                  goto :conda_ok
if exist "C:\Anaconda3\Scripts\activate.bat"                 set CONDA_ROOT=C:\Anaconda3&                  goto :conda_ok
if exist "C:\miniconda3\Scripts\activate.bat"                set CONDA_ROOT=C:\miniconda3&                 goto :conda_ok
if exist "C:\Miniconda3\Scripts\activate.bat"                set CONDA_ROOT=C:\Miniconda3&                 goto :conda_ok
if exist "C:\ProgramData\anaconda3\Scripts\activate.bat"     set CONDA_ROOT=C:\ProgramData\anaconda3&      goto :conda_ok
if exist "C:\ProgramData\Anaconda3\Scripts\activate.bat"     set CONDA_ROOT=C:\ProgramData\Anaconda3&      goto :conda_ok
if exist "C:\ProgramData\miniconda3\Scripts\activate.bat"    set CONDA_ROOT=C:\ProgramData\miniconda3&     goto :conda_ok
if exist "C:\ProgramData\Miniconda3\Scripts\activate.bat"    set CONDA_ROOT=C:\ProgramData\Miniconda3&     goto :conda_ok

echo HATA: Conda bulunamadi! Once 1_KURULUM.bat calistirin.
pause
exit /b 1

:conda_ok
call "%CONDA_ROOT%\Scripts\activate.bat" "%CONDA_ROOT%"

REM Test scriptini mimari_ai ortaminda calistir
cd /d "%~dp0.."
call conda run -n mimari_ai python kurulum\test_ortam.py

echo.
pause

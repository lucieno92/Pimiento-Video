@echo off
REM ============================================================
REM   Build Pimiento Video (.exe)
REM   Double-cliquez sur ce fichier pour generer l'application.
REM ============================================================

echo.
echo   ========================================
echo    Building Pimiento Video...
echo   ========================================
echo.

REM Installer PyInstaller si absent
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

REM Installer le moteur IA de voix (VoiceFixer) si absent
pip show voicefixer >nul 2>&1
if errorlevel 1 (
    echo Installing AI voice engine ^(VoiceFixer^)...
    pip install torch torchaudio
    pip install voicefixer
)

REM Nettoyer les anciens builds
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Construire
pyinstaller pimiento.spec --noconfirm

echo.
if exist "dist\Pimiento Video\Pimiento Video.exe" (
    echo   ========================================
    echo    SUCCESS!
    echo    Your app is in:  dist\Pimiento Video\
    echo    Run:  dist\Pimiento Video\Pimiento Video.exe
    echo   ========================================
) else (
    echo   ========================================
    echo    Build finished - check messages above
    echo    for any errors.
    echo   ========================================
)
echo.
pause

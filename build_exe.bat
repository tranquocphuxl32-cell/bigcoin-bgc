@echo off
REM =====================================================================
REM  BGC-Miner als .exe bauen (EINMALIG, auf Windows).
REM  Ergebnis: dist\BGC-Miner.exe  -> laeuft OHNE installiertes Python.
REM  Danach kann die .exe an jeden weitergegeben werden (nur Doppelklick).
REM =====================================================================
setlocal
cd /d "%~dp0"
title BGC-Miner .exe bauen

where python >nul 2>nul && (set PY=python) || (where py >nul 2>nul && (set PY=py))
if not defined PY (
  echo [!] Python 3 wird zum BAUEN benoetigt ^(nur einmal^): https://www.python.org/downloads/
  echo     Haken "Add python.exe to PATH" setzen. Danach diese Datei erneut starten.
  pause & exit /b 1
)

echo [1/3] PyInstaller + qrcode installieren/aktualisieren ...
%PY% -m pip install --upgrade pyinstaller qrcode || (echo Fehler bei pip & pause & exit /b 1)

echo [2/3] genesis sicherstellen ...
if not exist bgcfl_genesis.json %PY% bgcfl_genesis.py

echo [3/3] .exe bauen ...
%PY% -m PyInstaller --noconfirm BGC-Miner.spec || (echo Build-Fehler & pause & exit /b 1)

echo.
echo ============================================================
echo  FERTIG.  Die Datei liegt hier:  dist\BGC-Miner.exe
echo  Zum Starten: dist\BGC-Miner.exe doppelklicken.
echo  Weitergeben: BGC-Miner.exe + bgcfl_genesis.json zusammen kopieren.
echo ============================================================
echo.
pause
endlocal

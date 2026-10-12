@echo off
REM =====================================================================
REM  BGC-Miner - Ein-Klick-Start (Windows). Doppelklick zum Starten.
REM  Startet die Mining-App und oeffnet die Oberflaeche im Browser.
REM  Standardsprache: Deutsch (im Fenster oben rechts umschaltbar).
REM =====================================================================
setlocal
cd /d "%~dp0"
title BGC Miner

REM Python finden (python oder py)
where python >nul 2>nul
if %errorlevel%==0 (set PY=python) else (
  where py >nul 2>nul
  if %errorlevel%==0 (set PY=py) else (
    echo.
    echo [!] Python wurde nicht gefunden. Bitte Python 3 installieren:
    echo     https://www.python.org/downloads/  ^(Haken "Add to PATH" setzen^)
    echo.
    pause
    exit /b 1
  )
)

echo Starte BGC Miner ... Das Fenster bitte offen lassen.
echo Die Oberflaeche oeffnet sich im Browser. Zum Beenden dieses Fenster schliessen.
echo.

REM Optional einem Netzwerk beitreten: SEED unten eintragen (z.B. SET SEED=1.2.3.4:9333)
set SEED=
if defined SEED (
  %PY% bgc_app.py --peers %SEED% %*
) else (
  %PY% bgc_app.py %*
)

pause
endlocal

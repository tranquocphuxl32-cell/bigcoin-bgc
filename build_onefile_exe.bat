@echo off
REM =====================================================================
REM  BGC - tao MOT FILE .exe DUY NHAT tu BGC_Miner_1file.py (chay OHNE Python).
REM  Ket qua: dist\BGC-Miner.exe  -> gui MOT file nay cho may khach la chay dc.
REM  (Tu tao genesis ben trong, khong can file phu nao di kem.)
REM =====================================================================
setlocal
cd /d "%~dp0"
title BGC - tao 1 file .exe

where python >nul 2>nul && (set PY=python) || (where py >nul 2>nul && (set PY=py))
if not defined PY (
  echo [!] Can Python 3 de BUILD (chi 1 lan): https://www.python.org/downloads/
  echo     Nho tick "Add python.exe to PATH". Sau do chay lai file nay.
  pause & exit /b 1
)

echo [1/2] Cai PyInstaller + qrcode ...
%PY% -m pip install --upgrade pyinstaller qrcode || (echo Loi pip & pause & exit /b 1)

echo [2/2] Dong goi 1 file .exe ...
if exist bgc.ico (set IC=--icon bgc.ico) else (set IC=)
%PY% -m PyInstaller --onefile --name BGC-Miner %IC% ^
  --hidden-import qrcode --hidden-import qrcode.image.svg ^
  BGC_Miner_1file.py || (echo Loi build & pause & exit /b 1)

echo.
echo ============================================================
echo  XONG.  File DUY NHAT o:  dist\BGC-Miner.exe
echo  Gui file nay cho may khach -> nhap dup la DAO ra BGC.
echo  Tham gia mang: chay  BGC-Miner.exe --peers IP_MAY_ANH:9333
echo ============================================================
echo.
pause
endlocal

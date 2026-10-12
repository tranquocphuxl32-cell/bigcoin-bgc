@echo off
REM =====================================================================
REM  BGC - day ma nguon len GitHub (mot cu nhap).
REM  Lan dau: dan URL repo cua anh vao bien REPO ben duoi (hoac de trong,
REM  file se hoi). Can cai Git truoc: https://git-scm.com/downloads
REM =====================================================================
setlocal
cd /d "%~dp0"
title BGC - push GitHub

REM >>> Dan URL repo cua anh vao day (vi du: https://github.com/tenanh/bigcoin-bgc.git)
set REPO=

where git >nul 2>nul || (
  echo [!] Chua cai Git. Tai va cai: https://git-scm.com/downloads  roi chay lai.
  pause & exit /b 1
)

if "%REPO%"=="" set /p REPO=Dan URL repo GitHub (https://github.com/.../xxx.git):

REM An toan: chac chan khong day file vi len mang
echo.
echo [KIEM TRA] Cac file se KHONG day (da nam trong .gitignore):
echo   - my_bgc_wallet.json, *_wallet.json, bgcfl_data\, bgcfl_genesis.json
echo.

if not exist .git (
  git init
  git branch -M main
)

git add .
git status --short
echo.
set /p MSG=Ghi chu commit (Enter de dung mac dinh):
if "%MSG%"=="" set MSG=Update Bigcoin (BGC)

git commit -m "%MSG%"

REM Them remote neu chua co
git remote get-url origin >nul 2>nul || git remote add origin %REPO%

echo.
echo Dang day len GitHub ... (co the hoi dang nhap GitHub lan dau)
git push -u origin main

echo.
echo ============================================================
echo  XONG. Mo trang repo cua anh tren github.com de kiem tra.
echo ============================================================
pause
endlocal

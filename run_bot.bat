@echo off
rem ==========================================================================
rem  ORB-Bot daily run: build today's watchlist, then run the paper trader
rem  until the market closes. Everything is written to logs\runs\YYYY-MM-DD.log
rem
rem  Double-click it, or let Windows Task Scheduler start it every weekday
rem  morning (see setup_schedule.ps1). On weekends and market holidays the
rem  paper trader sees the market is closed and stops by itself.
rem ==========================================================================
cd /d "%~dp0"
title ORB-Bot is running - leave this window open
if not exist logs\runs mkdir logs\runs
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
set LOG=logs\runs\%TODAY%.log
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1

echo.
echo   ORB-Bot is running (PAPER trading, fake money).
echo   Scanner first, then the paper trader until the market closes.
echo.
echo   Leave this window open. It closes by itself after 4 PM.
echo   Closing it early stops the bot (open trades keep their stop orders at Alpaca).
echo.
echo   Full log: %CD%\%LOG%
echo.

echo ===== %DATE% %TIME%  scanner ===== >> "%LOG%"
".venv\Scripts\python.exe" scanners\run_daily.py --now >> "%LOG%" 2>&1

echo ===== %DATE% %TIME%  paper trader ===== >> "%LOG%"
".venv\Scripts\python.exe" fpb_paper_trader.py run >> "%LOG%" 2>&1

echo ===== %DATE% %TIME%  done ===== >> "%LOG%"

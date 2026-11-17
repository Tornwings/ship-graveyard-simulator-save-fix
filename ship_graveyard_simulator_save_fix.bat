@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%~dp0ship_graveyard_save_fix.py" %*
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo ERROR: Python 3 is required. Install it from python.org.
  ) else (
    python "%~dp0ship_graveyard_save_fix.py" %*
  )
)
echo.
pause

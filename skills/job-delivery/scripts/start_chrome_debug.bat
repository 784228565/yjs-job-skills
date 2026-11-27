@echo off
REM Start Chrome with remote debugging enabled (preserves login session).
REM
REM Hard requirements (verified on this machine):
REM   1. --disable-gpu --disable-gpu-compositing : without them
REM      Page.captureScreenshot hangs on every page in headed mode.
REM   2. Chrome >= 136 IGNORES --remote-debugging-port when used with the
REM      DEFAULT user-data-dir (verified on Chrome 150, 2026-07-25).
REM      Workaround: launch with a directory JUNCTION (UserData-CDP) that
REM      points to the real profile - same files, non-default path.
REM   3. The debug port only opens when Chrome STARTS with the flag and no
REM      other Chrome process is running.

set CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
set USER_DATA_DIR=%LOCALAPPDATA%\Google\Chrome\User Data
set CDP_PROFILE=%LOCALAPPDATA%\Google\Chrome\UserData-CDP
set DEBUG_PORT=9222

REM --- Guard: Chrome must be fully closed first -----------------------------
tasklist /FI "IMAGENAME eq chrome.exe" 2>nul | find /I "chrome.exe" >nul
if %errorlevel%==0 (
    echo [WARN] Chrome is already running. The debug port will NOT open.
    echo Close ALL Chrome windows first ^(check the system tray / "Continue running
    echo background apps" setting^), or let this script kill them.
    echo Your tabs will be restored on restart.
    choice /C YN /M "Kill all Chrome processes now"
    if errorlevel 2 (
        echo Aborted. Close Chrome manually and re-run this script.
        pause
        exit /b 1
    )
    taskkill /F /IM chrome.exe >nul 2>&1
    timeout /t 2 >nul
)

if not exist "%CHROME_PATH%" (
    echo Chrome not found at %CHROME_PATH%, trying x86 location...
    set CHROME_PATH=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe
)

REM --- Junction to the real profile (Chrome >=136 default-dir restriction) --
if not exist "%CDP_PROFILE%" (
    echo Creating profile junction: %CDP_PROFILE% -^> %USER_DATA_DIR%
    mklink /J "%CDP_PROFILE%" "%USER_DATA_DIR%" >nul
    if errorlevel 1 (
        echo [ERROR] mklink /J failed. Run this script as your normal user
        echo ^(junctions need no admin, but the target must exist^).
        pause
        exit /b 1
    )
)

echo Starting Chrome with debug port %DEBUG_PORT% ...
echo Profile ^(via junction^): %CDP_PROFILE%
start "" "%CHROME_PATH%" --remote-debugging-port=%DEBUG_PORT% --user-data-dir="%CDP_PROFILE%" --disable-gpu --disable-gpu-compositing --restore-last-session

echo.
echo Chrome started in debug mode. Keep it open while the delivery agent runs.
pause

@echo off
setlocal EnableDelayedExpansion

REM Fix for garbage characters (sets terminal to UTF-8)
chcp 65001 >nul

REM ============================================================================
REM ANSI COLOR SETUP
REM ============================================================================
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "B=%ESC%[94m"
set "R=%ESC%[91m"
set "C=%ESC%[96m"
set "W=%ESC%[97m"
set "N=%ESC%[0m"

pushd "%~dp0"

REM ============================================================================
REM PATH CONFIGURATION (Quoted to handle spaces)
REM ============================================================================
set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "OUT=%ROOT%\GitHub"
set "RELEASE=%OUT%\Release"
set "GITMAIN=%OUT%\Git Main"
set "LOGFILE=%OUT%\build-error.log"
set "VENV=%OUT%\.build_venv"
set "BUILDTMP=%OUT%\.build_work"

cls
echo %C%============================================================================
echo   %W%LAYERED %C%BUILD SYSTEM %N%                                     
echo %C%============================================================================%N%
echo   %W%Log File:%N%  %Y%"%LOGFILE%"%N%
echo   %W%Project:%N%   %Y%"%ROOT%"%N%
echo %C%----------------------------------------------------------------------------%N%

REM Create GitHub dir if missing
if not exist "%OUT%" mkdir "%OUT%"

REM Selective folder cleanup
if exist "%RELEASE%" (
    echo  %W%[%Y%^!%W%]%N% Clearing: %W%Release%N%
    rmdir /s /q "%RELEASE%"
)
if exist "%GITMAIN%" (
    echo  %W%[%Y%^!%W%]%N% Clearing: %W%Git Main%N%
    rmdir /s /q "%GITMAIN%"
)
mkdir "%RELEASE%"
mkdir "%GITMAIN%"

echo === build started %DATE% %TIME% === > "%LOGFILE%"

REM ============================================================================
REM BUILD PIPELINE
REM ============================================================================

call :stage 10 "Mirroring Source"
echo    %B%-%N% Mirroring to: %Y%Git Main%N%
robocopy "%ROOT%" "%GITMAIN%" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "%OUT%" "logs" "session" "__pycache__" ".pytest_cache" ".git" ".idea" ".vscode" ".venv" "venv" ".vs" ".claude" "build" "dist" /XF "*.pyc" "*.pyo" "*.log" "Bugs.txt" "bugs.txt" "*.spec" >> "%LOGFILE%" 2>&1
if %ERRORLEVEL% GEQ 8 goto :fail_robocopy

call :stage 25 "Python Environment"
set "PY=py"
%PY% --version >nul 2>&1 || set "PY=python"
echo    %B%-%N% Using Launcher: %G%%PY%%N%
echo    %B%-%N% Creating sandbox venv...
"%PY%" -m venv "%VENV%" >> "%LOGFILE%" 2>&1
set "PY_BIN=%VENV%\Scripts\python.exe"

call :stage 45 "Installing Dependencies"
echo    %B%-%N% Upgrading %G%pip%N%...
"%PY_BIN%" -m pip install --upgrade pip --quiet --no-input --disable-pip-version-check >> "%LOGFILE%" 2>&1

if exist "%ROOT%\requirements.txt" (
    echo    %B%^>%N% Installing from %C%requirements.txt%N%  %Y%^(live progress below^)%N%
    echo    %Y%[!]%N% PyQt6 + Pillow + NumPy total ~%W%100 MB%N% -- do %R%NOT%N% press any key.
    echo    %Y%[!]%N% "Installing collected packages" step extract ~3 min, no progress bar. Normal.
    echo.
    set "PYTHONIOENCODING=utf-8"
    set "PYTHONUNBUFFERED=1"
    powershell -NoProfile -Command "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); $OutputEncoding=[System.Text.UTF8Encoding]::new(); & '%PY_BIN%' -m pip install -r '%ROOT%\requirements.txt' --no-input --disable-pip-version-check --progress-bar on -v 2>&1 | ForEach-Object { $line = $_.ToString(); Write-Host $line; $line | Out-File -Append -FilePath '%LOGFILE%' -Encoding utf8 }"
    if errorlevel 1 goto :fail_pyinstaller
    echo.
)
echo    %B%^>%N% Package: %C%pyinstaller%N%
"%PY_BIN%" -m pip install pyinstaller --quiet --no-input --disable-pip-version-check >> "%LOGFILE%" 2>&1

call :stage 60 "Asset Processing"
if exist "%ROOT%\Icon.png" if not exist "%ROOT%\Icon.ico" (
    echo    %B%-%N% Converting %C%Icon.png%N%...
    "%PY_BIN%" -c "from PIL import Image; im=Image.open(r'%ROOT%\Icon.png').convert('RGBA'); im.save(r'%ROOT%\Icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])" >> "%LOGFILE%" 2>&1
)
set "ICONARG="
if exist "%ROOT%\Icon.ico" set ICONARG=--icon="%ROOT%\Icon.ico"

call :stage 75 "Compilation"
echo    %W%[%R%WAIT%W%] %Y%PyInstaller is freezing Layered.exe...%N%
if exist "%BUILDTMP%" rmdir /s /q "%BUILDTMP%"
"%PY_BIN%" -m PyInstaller --noconfirm --onefile --windowed --name Layered ^
    --collect-submodules app ^
    --collect-submodules PIL ^
    --collect-all PyQt6 ^
    %ICONARG% ^
    --distpath "%RELEASE%" ^
    --workpath "%BUILDTMP%\build" ^
    --specpath "%BUILDTMP%" ^
    "%ROOT%\main.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto :fail_pyinstaller

call :stage 95 "Final Assembly"
if exist "%ROOT%\Plugins" (
    echo    %B%-%N% Syncing: %Y%Plugins%N%
    robocopy "%ROOT%\Plugins" "%RELEASE%\Plugins" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "__pycache__" /XF "*.pyc" "*.pyo" >> "%LOGFILE%" 2>&1
)
for %%F in ("Icon.ico", "Icon.png", "README.md", "Changelog.md", "Create_tool_or_Brush.py") do (
    if exist "%ROOT%\%%~F" (
        echo    %B%^>%N% Copying: %W%%%~F%N%
        copy /Y "%ROOT%\%%~F" "%RELEASE%\" >nul
    )
)
if exist "%ROOT%\docs" (
    echo    %B%-%N% Syncing: %Y%docs%N%
    robocopy "%ROOT%\docs" "%RELEASE%\docs" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "__pycache__" /XF "*.pyc" "*.pyo" >> "%LOGFILE%" 2>&1
)

call :stage 100 "Cleaning Up"
if exist "%BUILDTMP%" rmdir /s /q "%BUILDTMP%"
if exist "%VENV%" rmdir /s /q "%VENV%"

echo.
echo %G%============================================================================
echo   BUILD SUCCESSFUL
echo %G%============================================================================%N%
echo   %W%Release EXE:%N%  %C%"%RELEASE%\Layered.exe"%N%
echo   %W%Git Source:%N%   %C%"%GITMAIN%"%N%
echo.
pause
popd
endlocal & exit /b 0

:stage
set "PCT=%~1"
set "MSG=%~2"
set /a "filled=%PCT% / 4"
set /a "empty=25 - %filled%"
set "BAR="
for /L %%i in (1,1,%filled%) do set "BAR=!BAR!█"
for /L %%i in (1,1,%empty%) do set "BAR=!BAR!░"
echo.
echo  %W%%BAR% %PCT%%%  %C%%MSG%%N%
exit /b

:fail_robocopy
echo.
echo  %R%[ERROR]%N% Robocopy failed.
goto :fail_end

:fail_pyinstaller
echo.
echo  %R%[ERROR]%N% PyInstaller failed. 
powershell -NoProfile -Command "Get-Content -Tail 10 '%LOGFILE%'"
goto :fail_end

:fail_end
echo %R%----------------------------------------------------------------------------
echo   BUILD FAILED. Check log: "%LOGFILE%"
echo ----------------------------------------------------------------------------%N%
pause
exit /b 1
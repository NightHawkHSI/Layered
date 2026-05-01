@echo off
REM ============================================================================
REM Layered build script.
REM Creates ./GitHub/Release  and  ./GitHub/Git Main
REM   Git Main : clean copy of source ready to push to a git repo
REM   Release  : Layered.exe + Plugins/
REM Full output captured to ./GitHub/build-error.log
REM ============================================================================

setlocal
pushd "%~dp0"

set "ROOT=%CD%"
set "OUT=%ROOT%\GitHub"
set "RELEASE=%OUT%\Release"
set "GITMAIN=%OUT%\Git Main"

if not exist "%OUT%"      mkdir "%OUT%"
if not exist "%RELEASE%"  mkdir "%RELEASE%"
if not exist "%GITMAIN%"  mkdir "%GITMAIN%"

set "LOGFILE=%OUT%\build-error.log"
echo [build] log: %LOGFILE%
echo === build started %DATE% %TIME% === > "%LOGFILE%"

call :body >> "%LOGFILE%" 2>&1
set RC=%ERRORLEVEL%

echo === build ended %DATE% %TIME% (rc=%RC%) === >> "%LOGFILE%"

type "%LOGFILE%"
echo.
if %RC% NEQ 0 (
    echo [build] FAILED. exit %RC%. log: %LOGFILE%
) else (
    echo [build] OK. log: %LOGFILE%
)
echo.
pause
popd
endlocal & exit /b %RC%


:body
echo [build] root: %ROOT%
echo [build] out : %OUT%

echo.
echo [build] mirroring source -^> "%GITMAIN%"
robocopy "%ROOT%" "%GITMAIN%" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "%OUT%" "logs" "__pycache__" ".git" ".idea" ".vscode" ".venv" "venv" ".vs" "build" "dist" /XF "*.pyc" "*.pyo" "*.log" "Bugs.txt" "*.spec"
set RC=%ERRORLEVEL%
echo [build] robocopy exit code: %RC%
if %RC% GEQ 8 (
    echo [build] robocopy failed.
    exit /b 1
)

echo.
echo [build] checking python
set "PY=py"
%PY% --version >nul 2>&1
if not errorlevel 1 goto :pyok
set "PY=python"
%PY% --version >nul 2>&1
if not errorlevel 1 goto :pyok
echo [build] no python launcher found. install Python from python.org
exit /b 1
:pyok
echo [build] using launcher: %PY%

echo [build] installing/upgrading dependencies
%PY% -m pip install --upgrade pip
if errorlevel 1 (
    echo [build] pip upgrade failed
    exit /b 1
)
%PY% -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
    echo [build] requirements install failed
    exit /b 1
)
%PY% -m pip install pyinstaller
if errorlevel 1 (
    echo [build] pyinstaller install failed
    exit /b 1
)

echo.
echo [build] building exe with PyInstaller
set "PYI=%PY% -m PyInstaller"

set "BUILDTMP=%OUT%\_pyinstaller"
if exist "%BUILDTMP%" rmdir /s /q "%BUILDTMP%"

REM --- generate Icon.ico from Icon.png if missing.
if not exist "%ROOT%\Icon.ico" if exist "%ROOT%\Icon.png" (
    echo [build] generating Icon.ico from Icon.png
    %PY% -c "from PIL import Image; im=Image.open(r'%ROOT%\Icon.png').convert('RGBA'); im.save(r'%ROOT%\Icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if errorlevel 1 (
        echo [build] icon generation failed
        exit /b 1
    )
)

set ICONARG=
if exist "%ROOT%\Icon.ico" set ICONARG=--icon="%ROOT%\Icon.ico"

%PYI% --noconfirm --onefile --windowed --name Layered ^
    --collect-submodules app ^
    %ICONARG% ^
    --distpath "%RELEASE%" ^
    --workpath "%BUILDTMP%\build" ^
    --specpath "%BUILDTMP%" ^
    "%ROOT%\main.py"
if errorlevel 1 (
    echo [build] pyinstaller failed
    exit /b 1
)

echo [build] copying Plugins next to exe
robocopy "%ROOT%\Plugins" "%RELEASE%\Plugins" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "__pycache__" /XF "*.pyc" "*.pyo"
if %ERRORLEVEL% GEQ 8 (
    echo [build] plugin copy failed
    exit /b 1
)

REM Ship icon next to the exe so the file-explorer thumbnail uses it.
if exist "%ROOT%\Icon.ico" copy /Y "%ROOT%\Icon.ico" "%RELEASE%\Icon.ico" >nul
if exist "%ROOT%\Icon.png" copy /Y "%ROOT%\Icon.png" "%RELEASE%\Icon.png" >nul
if exist "%ROOT%\README.md"    copy /Y "%ROOT%\README.md"    "%RELEASE%\README.md"    >nul
if exist "%ROOT%\Changelog.md" copy /Y "%ROOT%\Changelog.md" "%RELEASE%\Changelog.md" >nul

rmdir /s /q "%BUILDTMP%"

echo.
echo [build] done.
echo   Git Main : %GITMAIN%
echo   Release  : %RELEASE%\Layered.exe
exit /b 0

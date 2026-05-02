@echo off
REM ============================================================================
REM Layered build script.
REM Creates ./GitHub/Release  and  ./GitHub/Git Main
REM   Git Main : clean copy of source ready to push to a git repo
REM   Release  : Layered.exe + Plugins/
REM Verbose tool output captured to ./GitHub/build-error.log
REM Stage progress (0-100%) printed live to the console.
REM ============================================================================

setlocal EnableDelayedExpansion
pushd "%~dp0"

set "ROOT=%CD%"
set "OUT=%ROOT%\GitHub"
set "RELEASE=%OUT%\Release"
set "GITMAIN=%OUT%\Git Main"

if not exist "%OUT%"      mkdir "%OUT%"
if not exist "%RELEASE%"  mkdir "%RELEASE%"
if not exist "%GITMAIN%"  mkdir "%GITMAIN%"

set "LOGFILE=%OUT%\build-error.log"
echo === build started %DATE% %TIME% === > "%LOGFILE%"

set "T0=%TIME%"
call :stage   0 "starting"
call :stage   5 "mirroring source -> Git Main"
robocopy "%ROOT%" "%GITMAIN%" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "%OUT%" "logs" "__pycache__" ".git" ".idea" ".vscode" ".venv" "venv" ".vs" "build" "dist" /XF "*.pyc" "*.pyo" "*.log" "Bugs.txt" "*.spec" >> "%LOGFILE%" 2>&1
set RC=%ERRORLEVEL%
if %RC% GEQ 8 (
    call :fail "robocopy failed (rc=%RC%)"
    goto :end
)

call :stage  15 "checking python launcher"
set "PY=py"
%PY% --version >nul 2>&1
if errorlevel 1 (
    set "PY=python"
    %PY% --version >nul 2>&1
    if errorlevel 1 (
        call :fail "no python launcher found. install Python from python.org"
        goto :end
    )
)
echo [build] using launcher: %PY% >> "%LOGFILE%"

call :stage  20 "upgrading pip"
%PY% -m pip install --upgrade pip >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :fail "pip upgrade failed"
    goto :end
)

call :stage  35 "installing requirements"
%PY% -m pip install -r "%ROOT%\requirements.txt" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :fail "requirements install failed"
    goto :end
)

call :stage  50 "installing PyInstaller"
%PY% -m pip install pyinstaller >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :fail "pyinstaller install failed"
    goto :end
)

set "BUILDTMP=%OUT%\_pyinstaller"
if exist "%BUILDTMP%" rmdir /s /q "%BUILDTMP%"

if not exist "%ROOT%\Icon.ico" if exist "%ROOT%\Icon.png" (
    call :stage 55 "generating Icon.ico from Icon.png"
    %PY% -c "from PIL import Image; im=Image.open(r'%ROOT%\Icon.png').convert('RGBA'); im.save(r'%ROOT%\Icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])" >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
        call :fail "icon generation failed"
        goto :end
    )
)

set ICONARG=
if exist "%ROOT%\Icon.ico" set ICONARG=--icon="%ROOT%\Icon.ico"

call :stage  60 "freezing exe with PyInstaller (this is the slow step)"
%PY% -m PyInstaller --noconfirm --onefile --windowed --name Layered ^
    --collect-submodules app ^
    %ICONARG% ^
    --distpath "%RELEASE%" ^
    --workpath "%BUILDTMP%\build" ^
    --specpath "%BUILDTMP%" ^
    "%ROOT%\main.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :fail "pyinstaller failed (see log tail below)"
    echo --- log tail ---
    powershell -NoProfile -Command "Get-Content -Tail 40 '%LOGFILE%'"
    goto :end
)

call :stage  92 "copying Plugins next to exe"
robocopy "%ROOT%\Plugins" "%RELEASE%\Plugins" *.* /MIR /NFL /NDL /NJH /NJS /NP /XD "__pycache__" /XF "*.pyc" "*.pyo" >> "%LOGFILE%" 2>&1
if %ERRORLEVEL% GEQ 8 (
    call :fail "plugin copy failed"
    goto :end
)

call :stage  96 "copying icon, README, changelog"
if exist "%ROOT%\Icon.ico"     copy /Y "%ROOT%\Icon.ico"     "%RELEASE%\Icon.ico"     >nul
if exist "%ROOT%\Icon.png"     copy /Y "%ROOT%\Icon.png"     "%RELEASE%\Icon.png"     >nul
if exist "%ROOT%\README.md"    copy /Y "%ROOT%\README.md"    "%RELEASE%\README.md"    >nul
if exist "%ROOT%\Changelog.md" copy /Y "%ROOT%\Changelog.md" "%RELEASE%\Changelog.md" >nul

if exist "%BUILDTMP%" rmdir /s /q "%BUILDTMP%"

call :stage 100 "done"
echo === build ended %DATE% %TIME% (ok) === >> "%LOGFILE%"
echo.
echo [build] OK
echo   Git Main : %GITMAIN%
echo   Release  : %RELEASE%\Layered.exe
echo   Log      : %LOGFILE%
echo.
pause
popd
endlocal & exit /b 0


:stage
REM Args: %1 = percent (1-3 chars), %2..* = message
set "PCT=%~1"
shift
set "MSG=%~1"
:stage_concat
shift
if not "%~1"=="" (
    set "MSG=!MSG! %~1"
    goto :stage_concat
)
REM Right-align percent in 3 cols.
set "PADP=  %PCT%"
set "PADP=!PADP:~-3!"
echo [!PADP!%%] !MSG!
echo [!PADP!%%] !MSG! >> "%LOGFILE%"
goto :eof


:fail
echo.
echo [build] FAILED: %~1
echo [build] log: %LOGFILE%
echo === build ended %DATE% %TIME% (FAILED: %~1) === >> "%LOGFILE%"
goto :eof


:end
echo.
pause
popd
endlocal & exit /b 1

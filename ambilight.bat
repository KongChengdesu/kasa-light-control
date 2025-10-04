@echo off
REM ambilight.bat - launch ambilight.py with optional interval argument
REM Usage: ambilight.bat [interval_seconds]

REM Change to script directory (handles spaces in path)
pushd "%~dp0"

echo Starting ambilight... (press Ctrl+C in this window to stop)

REM Prefer the Python launcher if available, otherwise use python from PATH
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 ambilight.py %*
) else (
    python "ambilight.py" %*
)

popd

@echo off
cd /d "%~dp0.."
echo Starting CAM Kernel Web UI...
echo Open http://127.0.0.1:8910 in your browser
python -c "import OCP" >nul 2>&1
if errorlevel 1 (
  echo WARNING: STEP import is unavailable because cadquery-ocp is not installed.
  echo Install it with: python -m pip install -e ".\cam_kernel[occt]"
  echo JSON feature import will still work.
)
set PYTHONPATH=%~dp0..;%PYTHONPATH%
python -c "import sys; sys.path.insert(0, '.'); from cam_kernel.cam_kernel.web.server import main; main()"
pause

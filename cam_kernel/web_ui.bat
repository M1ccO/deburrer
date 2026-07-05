@echo off
cd /d "%~dp0.."
echo Starting CAM Kernel Web UI...
echo Open http://127.0.0.1:8910 in your browser
set PYTHONPATH=%~dp0..;%PYTHONPATH%
python -c "import sys; sys.path.insert(0, '.'); from cam_kernel.cam_kernel.web.server import main; main()"
pause

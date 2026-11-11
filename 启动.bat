@echo off
cd /d "%~dp0"
python -c "import PySide6" 1>nul 2>nul
if errorlevel 1 (
  echo Installing interface libraries...
  python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
python -m app
if errorlevel 1 pause

@echo off
chcp 65001 >nul

cd /d "%~dp0"

echo ========================================
echo   Installing dependencies...
echo ========================================

pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install pymysql -i https://pypi.tuna.tsinghua.edu.cn/simple
playwright install chromium

echo ========================================
echo   Done! Now run: start.bat
echo ========================================
pause

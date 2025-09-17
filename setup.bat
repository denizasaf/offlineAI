@echo off
winget install python3
pip install -r requirements.txt
python3 -m venv env 
call env\Scripts\activate.bat
pip install pyinstaller requests beautifulsoup4 yt-dlp torch transformers PyPDF2
pyinstaller --onefile --windowed ai.py

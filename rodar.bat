@echo off
REM TestingStudio Web - dois cliques para abrir no navegador
cd /d "%~dp0"
python -c "import streamlit, google.genai" 2>nul || (
    echo Instalando as dependencias pela primeira vez...
    python -m pip install -r requirements.txt
)
python -m streamlit run app.py
pause

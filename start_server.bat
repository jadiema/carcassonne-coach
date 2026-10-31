@echo off
cd /d "%~dp0"
echo ================================================
echo   Carcassonne Coach - Serveur local
echo ================================================
echo.
echo   Dossier: %CD%
echo.
echo Installation des dependances...
pip install -r requirements.txt --quiet
echo.
echo Lancement du serveur sur http://localhost:5555
echo Laissez cette fenetre ouverte pendant que vous jouez.
echo Appuyez sur Ctrl+C pour arreter.
echo.
python server.py
pause

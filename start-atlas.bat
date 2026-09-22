@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe manage.py run_atlas --open
) else (
  echo Creez l'environnement Python et installez requirements.txt.
  echo Voir docs\FOUNDATION.md pour les instructions PostgreSQL.
)
pause

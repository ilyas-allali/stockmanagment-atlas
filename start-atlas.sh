#!/bin/sh
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Créez l'environnement Python et installez requirements.txt. Voir docs/FOUNDATION.md."
  exit 1
fi
exec .venv/bin/python manage.py run_atlas --open "$@"

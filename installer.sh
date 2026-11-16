#!/bin/sh
# Installe claude-jobs : environnement Python, dépendances, fichiers de configuration. À relancer sans risque.
set -e
cd "$(dirname "$0")"

echo "▸ Vérification de Python…"
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 introuvable. macOS : installe-le depuis https://www.python.org ou avec « brew install python »." >&2
  exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "❌ Python 3.9 ou plus récent est nécessaire (tu as $(python3 --version))." >&2; exit 1; }

echo "▸ Création de l'environnement Python (.venv)…"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt
echo "▸ Recherche automatique LinkedIn / Indeed (python-jobspy, facultatif)…"
.venv/bin/python -m pip install -q python-jobspy || echo "  ⚠️  python-jobspy n'a pas pu s'installer : ./jobs chercher ne marchera pas, les agents de Claude, si."

echo "▸ Fichiers personnels (jamais écrasés s'ils existent)…"
[ -f preferences.yml ] || { cp exemples/preferences.exemple.yml preferences.yml; echo "  preferences.yml créé"; }
[ -f cv.md ] || { cp exemples/cv.exemple.md cv.md; echo "  cv.md créé"; }
[ -f journal.md ] || { cp exemples/journal.exemple.md journal.md; echo "  journal.md créé"; }
mkdir -p data/tmp candidatures
chmod +x jobs

echo ""
./jobs verifier || true
echo ""
echo "Prochaine étape, au choix :"
echo "  • dans Claude Code (lancé dans ce dossier) : /configurer   ← Claude lit ton CV et te pose les questions"
echo "  • ou dans le navigateur : ./jobs serveur                   ← page « Mon profil »"
echo "Envie de voir à quoi ça ressemble d'abord ? ./jobs demo"

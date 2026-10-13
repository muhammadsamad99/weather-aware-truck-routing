#!/usr/bin/env bash
# The production build (Render runs this): Python packages, the React app, then Django's static files.
set -o errexit -o nounset -o pipefail

pip install --requirement backend/requirements.txt
npm ci --prefix frontend
npm run build --prefix frontend
python -m whitenoise.compress frontend/dist  # gzip copies of the app, which WhiteNoise serves when accepted
python backend/manage.py collectstatic --noinput

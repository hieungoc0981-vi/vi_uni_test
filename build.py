"""Prepare public assets for Vercel. Does not access the database or load Flask."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
assets = root / 'public' / 'static'
assets.mkdir(parents=True, exist_ok=True)
for name in ('app.js', 'style.css'):
    shutil.copyfile(root / 'static' / name, assets / name)
print('Prepared public/static/app.js and public/static/style.css')

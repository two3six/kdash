# kdash2 — Kindle PW3 e-ink dashboard (server-rendered)
`render.py` (Python 3.9+, Pillow) draws a 1072x1448 grayscale PNG: weather (Open-Meteo), hourly temp/rain,
5-day forecast, sunrise/sunset + moon, Dallas sports (ESPN), markets (Yahoo chart API), headlines (RSS).
Each source fails independently. Fonts bundled in fonts/ (DejaVu, free license).
GitHub Actions (.github/workflows/render.yml) renders every 15 min and publishes to the gh-pages branch:
https://<user>.github.io/<repo>/dash.png  -> set IMAGE_URL in /mnt/us/kdash/config.sh on the Kindle.

# Packaging & sharing TradeLens

Two ways to share the app: a **GitHub repository** (best for ongoing sharing and updates)
or a **ZIP file** (simplest for sending to one person). Both are covered below.

> **Before you share — the one rule:** never include your own statement files. Anything in
> `data/*.csv` contains your account number and trade history. The `.gitignore` and the
> prebuilt ZIP already exclude them; just don't add them back.

## What belongs in a share

Include: `app.py`, `ibkr_analytics.py`, `sectors.py`, `enrich_sectors.py`,
`requirements.txt`, `run_dashboard.bat`, `.streamlit/config.toml`, `README.md`,
`USER_GUIDE.md`, `LICENSE`, `.gitignore`, `data/README.txt`, `output/.gitkeep`.

Exclude: `data/*.csv` (your statements), `output/*`, `__pycache__/`, `*.log`, screenshots,
and any scratch scripts.

---

## Option A — Share as a ZIP (quickest)

A ready-to-send ZIP has already been built for you: **`TradeLens.zip`** (no statements
inside). Just send that file. The recipient unzips it and follows `USER_GUIDE.md`.

To rebuild it yourself later (e.g. after changes), from inside the project folder:

**macOS / Linux:**
```bash
cd ..
zip -r TradeLens.zip trading-dashboard \
  -x "*/data/*.csv" "*/output/*" "*/__pycache__/*" "*.log" "*.png" \
     "*/shoot*.py" "*/probe*.py" "*/diag.py"
```

**Windows (PowerShell):** the simplest safe route is to copy the project to a temp folder,
delete `data\*.csv` and `__pycache__` from the copy, then right-click → *Send to →
Compressed (zipped) folder*.

---

## Option B — Publish to GitHub (best for updates)

**One-time setup:** install [git](https://git-scm.com/downloads) and, optionally, the
[GitHub CLI](https://cli.github.com/) (`gh`). Create a free account at github.com.

From inside the `trading-dashboard` folder:

```bash
git init
git add .
git status          # confirm NO .csv statements are listed (they should be ignored)
git commit -m "TradeLens: IBKR trading performance dashboard"
```

Then create the remote and push. **With the GitHub CLI:**

```bash
gh repo create tradelens --public --source=. --remote=origin --push
```

**Or manually:** create an empty repo on github.com (no README), then:

```bash
git branch -M main
git remote add origin https://github.com/<your-username>/tradelens.git
git push -u origin main
```

Your app is now at `https://github.com/<your-username>/tradelens`. People can download it
(green **Code → Download ZIP**) or clone it:

```bash
git clone https://github.com/<your-username>/tradelens.git
```

**Public vs private:** use `--public` to let anyone see and use it; use `--private` to keep
it to invited collaborators only. You can change this later in the repo's Settings.

**To push future changes:**
```bash
git add .
git commit -m "Describe what changed"
git push
```

**Double-check before the first push:** run `git status` and make sure no file ending in
`.csv` appears. If one does, it means it isn't being ignored — remove it with
`git rm --cached data/yourfile.csv` before committing.

---

## Optional niceties for a public repo

- Add a couple of **screenshots** to the README (use Privacy mode when capturing).
- Consider **Streamlit Community Cloud** (share.streamlit.io) to host it as a live website
  from your GitHub repo — but note anyone with the link could upload a statement, so only
  do this if you're comfortable with a public tool. For personal/financial data, running
  locally is the safer default.
- Pin exact package versions in `requirements.txt` if you want maximum reproducibility.

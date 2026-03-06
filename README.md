# Stage B5 Manual (Standalone)

Standalone extraction of Athena Stage B5 Manual annotator.

This repo contains:
- A runnable Flask app with B5 Manual endpoints at `/api/athena/b5/manual/*`
- The full B5 Manual UI (plot + pane controls + save/finalize flow)
- B5 workbook write logic (`B5_Reps` and `B5_Dashboard` generation)

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start app:

```bash
python app.py
```

4. Open:

```text
http://127.0.0.1:5151/
```

## Student Setup Guide

- See `requirements.md` for install steps and relative path usage.
- Use relative folders in the UI (for example `./data/enriched` and `./data/enriched-rep`).

## Main endpoints

- `POST /api/athena/b5/manual/scan`
- `POST /api/athena/b5/manual/next`
- `POST /api/athena/b5/manual/plan`
- `POST /api/athena/b5/manual/pane`
- `POST /api/athena/b5/manual/prepare`
- `POST /api/athena/b5/manual/apply`
- `POST /api/athena/b5/manual/apply_batch`
- `POST /api/athena/b5/manual/adjust_label_window`
- `POST /api/athena/b5/manual/finalize`

## Notes

- `finalize` moves the source file into an `archived/` folder and writes `<filename>.done` in enriched-rep.
- `apply` writes manual marker columns and rebuilds `B5_Reps` + `B5_Dashboard` sheets.
- Resume state is stored in browser `localStorage`.

## Push to GitHub

If this local folder is already connected to a remote, push as usual.
If not:

```bash
git add .
git commit -m "Extract standalone Stage B5 Manual app"
git branch -M main
git remote add origin <YOUR_GITHUB_REPO_URL>
git push -u origin main
```

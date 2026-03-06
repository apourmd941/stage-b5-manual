# Requirements And Setup

## What Students Need

- Python 3.10+ (3.11 or 3.12 recommended)
- `pip`
- Internet access for first-time package install

## Install

From the repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5151/
```

## Path Rules (Relative, Not Absolute)

Use relative paths in the UI inputs.

Examples:

- Enriched folder: `./data/enriched`
- Enriched-Rep folder: `./data/enriched-rep`
- File glob: `*.xlsx`

These paths are resolved relative to where you run `python app.py` (the repo root).

Avoid Mac-only absolute paths like:

- `/Users/yourname/...`

## Folder Layout Example

```text
stage-b5-manual/
  data/
    enriched/
    enriched-rep/
```


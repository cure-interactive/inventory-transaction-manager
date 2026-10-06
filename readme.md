# Inventory Transaction Manager

**Sunset October 6, 2026. No longer maintained.**

Desktop inventory transaction tracker with transaction entry, aliases, overview tables, custom fields, CSV export, and project-directory persistence.

## Requirements

- Python 3.10+
- Dependencies from `requirements.txt`

## Install

```bash
python setup.py --venv
```

Or manually:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

On Linux or macOS, activate the virtual environment with `source .venv/bin/activate`.

## Run Desktop App

```bash
python inventory_transaction_manager.py
```

The app writes local runtime settings to `config.json` beside the script. Project data is stored in the selected project directory.

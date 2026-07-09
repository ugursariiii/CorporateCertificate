# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file PyQt6 desktop app (`main.py`) for the school's "Kurumsal İletişim / Corporate Communications" unit. It tracks corporate certificate programs (Siemens, Cervantes, Özyeğin, etc.) per academic term, school, and grade level, storing everything in a local SQLite database (`corporate_certificates.db`). UI text and code comments are in Turkish.

## Commands

The project uses a `.venv` (Python 3.14) and has no `requirements.txt`. The only runtime dependency is PyQt6.

```bash
# Run the app (from repo root, with venv active)
python main.py

# Install the sole dependency
pip install PyQt6

# Build a standalone Windows executable (output in dist/CorporateCertificate/)
pyinstaller CorporateCertificate.spec
```

There are no tests, linters, or CI configured.

## Architecture

Everything lives in `main.py`, organized top-to-bottom into four layers separated by comment banners:

1. **Domain constants** — `OKULLAR` (schools), `SEVIYELER` (grade levels, ordered `LH, 9, 10, 11, 12`), and `ONCEKI_SEVIYE`, a map from each level to the one below it. `LH` (prep/Hazırlık) is the terminal level.

2. **`Database` class** — thin SQLite wrapper over a single `activities` table (`id, donem, okul, seviye, etkinlik_adi`). Every method opens and closes its own connection via `contextlib.closing`; there is no shared/persistent connection. The schema is created lazily on construction.

3. **Retrospective algorithm** — `generate_retrospective(db, donem, okul, seviye)` is the core domain logic. Starting from a chosen term+level, it walks *backwards in time*: each step goes one academic year back (`donem_bir_yil_geri`, e.g. `2025-2026` → `2024-2025`) **and** one grade level down (`12 → 11 → … → 9 → LH`), stopping after `LH`. It returns one report row per step, including a placeholder row when no certificate is found for that step (so the trace stays visible). Term format is always `YYYY-YYYY`.

4. **`MainWindow` (UI)** — two tabs: "Yeni Kayıt Ekle" (data entry) and "Listele" (query/report). All styling comes from the `CORPORATE_QSS` stylesheet string.

### Things worth knowing before editing

- **Multi-record save:** the entry form uses checkbox groups for schools and levels; saving inserts one row per *school × level* combination (see `_on_save_activity`).
- **Windows title bar coloring:** `_apply_native_titlebar_color` calls the DWM API via `ctypes` to tint the native caption bar (Windows 11 22000+ only); it silently no-ops elsewhere. QSS cannot style the native caption.
- **Styled QFrame background:** any `QFrame` needing a QSS background color must set `WA_StyledBackground` (as `HeaderBar` does), or the background won't paint.
- **Delete flow:** report rows backed by a real record get a per-row "Sil" button wired with a captured `r` default-arg lambda; placeholder rows (`id is None`) do not.
- **Export / Print** buttons are intentional placeholders (`_on_export_placeholder`, `_on_print_placeholder`) — hooks for future pandas/openpyxl and QPrinter code.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Single-file PyQt6 desktop app (`main.py`) for the school's "Kurumsal İletişim / Corporate Communications" unit. It tracks corporate certificate programs (Siemens, Cervantes, Özyeğin, etc.) per academic term, school, and grade level, storing everything in a remote **MSSQL** database (`CorporateCertificate` on SQL Server 2022 at `94.102.74.165`, accessed via **pymssql**). Wherever the app runs it talks to that one central server — there is no local database file. UI text and code comments are in Turkish. The legacy `corporate_certificates.db` SQLite file is left in the repo for reference only — nothing reads it anymore.

**Why pymssql and not pyodbc:** pyodbc needs "ODBC Driver 18 for SQL Server" installed on the machine, and PyInstaller cannot bundle that (it is a registry-registered system component). pymssql ships its TDS client (FreeTDS) inside the wheel, so the frozen exe runs on any Windows machine with no prerequisites. Do not switch back to pyodbc without solving that distribution problem.

## Commands

The project uses a `.venv` (Python 3.14). Runtime dependencies: PyQt6 and pymssql.

```bash
# Run the app (from repo root, with venv active)
python main.py

# Install dependencies
pip install -r requirements.txt

# Apply the DB schema manually (the app also does this on startup)
sqlcmd -S 94.102.74.165 -U sa -P <parola> -d CorporateCertificate -i schema.sql

# Build the distributable single-file exe (output: dist/CorporateCertificate.exe)
pyinstaller --noconfirm --clean CorporateCertificate.spec
```

The spec is **onefile** (no `COLLECT`): the whole app is one ~38 MB `.exe` that is copied and run as-is. Nothing else gets shipped alongside it — in particular do not copy a `.db` file next to it.

There are no tests, linters, or CI configured.

## Architecture

Everything lives in `main.py`, organized top-to-bottom into four layers separated by comment banners:

1. **Domain constants** — `OKULLAR` (schools), `SEVIYELER` (grade levels, ordered `LH, 9, 10, 11, 12`), and `ONCEKI_SEVIYE`, a map from each level to the one below it. `LH` (prep/Hazırlık) is the terminal level.

2. **`Database` class** — thin pymssql wrapper over three tables: `dbo.activities` (`id INT IDENTITY, donem, okul, seviye, etkinlik_adi`, all `NVARCHAR`), `dbo.files` (attachment *metadata only* — `dosya_adi`, `saklanan_ad`, `boyut`, `yuklenme_tarihi`), and the many-to-many junction `dbo.activity_files`. Every method opens and closes its own connection via `contextlib.closing` (helpers `_fetch` / `_execute` / `_insert_returning_id`); there is no shared/persistent connection or pooling layer of our own. The schema is created lazily on construction by running `DDL_STATEMENTS`, which must be kept in sync with `schema.sql` (same DDL, minus the sqlcmd-only `GO` separators). Connections pass `charset="UTF-8"` — dropping it mangles Turkish characters.

   **Parameter style is `%s`, not `?`** — that is pymssql's placeholder (values are still bound by the driver, so it is not string interpolation and remains injection-safe). A stray `?` will fail at runtime. Literal `%` in SQL must be written `%%`.

   Connection settings are module-level constants (`DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), each overridable at runtime via `CORPCERT_SERVER` / `CORPCERT_DB` / `CORPCERT_USER` / `CORPCERT_PASSWORD` env vars — that is how you point a *already-built* exe at a different server without rebuilding.

3. **Retrospective algorithm** — `generate_retrospective(db, donem, okul, seviye)` is the core domain logic. Starting from a chosen term+level, it walks *backwards in time*: each step goes one academic year back (`donem_bir_yil_geri`, e.g. `2025-2026` → `2024-2025`) **and** one grade level down (`12 → 11 → … → 9 → LH`), stopping after `LH`. It returns one report row per step, including a placeholder row when no certificate is found for that step (so the trace stays visible). Term format is always `YYYY-YYYY`.

4. **`MainWindow` (UI)** — two tabs: "Yeni Kayıt Ekle" (data entry) and "Listele" (query/report). All styling comes from the `CORPORATE_QSS` stylesheet string.

### Things worth knowing before editing

- **Multi-record save:** the entry form uses checkbox groups for schools and levels; saving inserts one row per *school × level* combination (see `_on_save_activity`).
- **File attachments live on a network share, not in the database.** Files are copied to `DOSYA_KLASORU` (`\\172.16.0.201\Kurumsal_Video\ProgramFiles\CorporateCertificate\dosyalar`, overridable via `CORPCERT_DOSYA_KLASORU`); `dbo.files` only records metadata. The share I/O is a set of module-level functions (`depo_klasoru`, `depo_yolu`, `depoya_kopyala`, `depodan_sil`, `saklama_adi_uret`) — `Database` calls `depodan_sil` when rows go away, but nothing else does file I/O.
  - `saklama_adi_uret` gives each upload a collision-proof name on the share (`2025 Rapor.pdf` → `2025_Rapor_9f3c1ab2.pdf`); the user-facing original stays in `dosya_adi`. Never write the original name straight to the share — two users uploading `rapor.pdf` would overwrite each other.
  - **Save order matters:** `_on_save_activity` copies every file to the share *before* touching the DB, so an unreachable share aborts with nothing written; if the DB write then fails, the copies are rolled back with `depodan_sil`.
  - Entry form buffers picks in `self.m_dosyalar` as `(name, source_path, size)` — paths, not contents; nothing is read into memory. Each file is copied **once** and linked to every activity row the save created (a 2-school × 5-level save = one file on the share, not ten).
  - **Adding files to an existing record** is `EkDosyalarDialog._on_add_files` — same share-before-DB order, but its rollback is narrower: a copy is only removed if `add_file` never wrote a row for it (`yazilanlar` tracks that). Deleting a copy whose `dbo.files` row survived would leave the DB pointing at a missing file; an orphan row with the file still present is the safer failure, and `_sahipsiz_dosyalari_temizle` clears it later.
- **Allowed types** come from the `IZINLI_UZANTILAR` dict (pdf / doc / docx / xls / xlsx / xlsm / ppt / pptx / txt). It is the single source of truth: the `QFileDialog` filter (`DOSYA_FILTRESI`), the user-facing type list (`IZINLI_TURLER_METNI`) and the `uzanti_izinli` check are all derived from it, so a new type only needs a new dict entry. The dialog filter alone is not enough — users can type a filename manually, so the module-level `dosya_secimlerini_dogrula` re-checks type, size and duplicate names for **both** entry points (`_on_pick_files` and `_on_add_files`) — keep new pickers going through it.
- **Orphan cleanup spans both stores:** deleting an activity drops junction rows via `ON DELETE CASCADE`, leaving unreferenced `dbo.files` rows; `_sahipsiz_dosyalari_temizle` deletes them with `OUTPUT DELETED.saklanan_ad` and hands the names to `depodan_sil` so the physical files go too. A file linked to several activities survives until the last link is gone. `depodan_sil` swallows `OSError` on purpose — an unreachable share must not fail a delete that already succeeded in the DB (the cost is an occasional stranded file).
- **`find_activities` returns triples** `(id, etkinlik_adi, dosya_sayisi)`, and `generate_retrospective` puts `dosya_sayisi` on every report row (0 on placeholders) — the report table reads it to label the Dosyalar cell "Dosyalar (n)" or "Dosya Ekle". Both open the same `EkDosyalarDialog`; only placeholder rows (`id is None`) get no button at all. The dialog sets `degisti` on add *or* delete, and `_on_show_files` re-runs the report so the count updates.
- **Windows title bar coloring:** `_apply_native_titlebar_color` calls the DWM API via `ctypes` to tint the native caption bar (Windows 11 22000+ only); it silently no-ops elsewhere. QSS cannot style the native caption.
- **Styled QFrame background:** any `QFrame` needing a QSS background color must set `WA_StyledBackground` (as `HeaderBar` does), or the background won't paint.
- **Network failures are expected:** every DB call can raise `pymssql.Error` because the server is remote, and every attachment call can raise `OSError` because the share is remote too. Call sites handle it — `main()` shows a "bağlanılamadı" dialog and exits if the initial connect fails, `_refresh_donem_combos` degrades to a status-bar warning, and the save/delete/report handlers show a `QMessageBox.critical`. Any new DB call site needs the same treatment.
- **Delete flow:** report rows backed by a real record get a per-row "Sil" button wired with a captured `r` default-arg lambda; placeholder rows (`id is None`) do not.
- **Export** (`_on_export_report`) writes the last generated report to CSV using the stdlib `csv` module — no pandas/openpyxl dependency, so the onefile exe stays as-is. It exports `self.son_rapor` (the row dicts stashed by `_on_generate_report`), not the `QTableWidget`, because the Dosyalar/İşlem columns hold buttons rather than text. Excel-compatibility details that must not be dropped: `encoding="utf-8-sig"` (BOM, or Turkish characters break in Excel), `delimiter=";"` (Turkish Excel's list separator), and `newline=""` (otherwise blank lines between rows on Windows).
- **Print** (`_on_print_report`) renders the same `self.son_rapor` rows as HTML (`_rapor_html`) into a `QTextDocument` and shows a `QPrintPreviewDialog` (A4 portrait). Qt's rich text engine supports only a subset of CSS, so the report styling is inline and table borders use HTML attributes — don't reach for a stylesheet. Row values go through `html.escape`. Importing `PyQt6.QtPrintSupport` is what makes PyInstaller bundle the Qt print DLLs; the spec has no Qt excludes, so nothing else is needed.

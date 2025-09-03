#!/usr/bin/env python3
"""
Fetch Bitcoin RHODL Ratio from CoinGlass (full history), save JSON in ./json_data/,
and write only columns A & B on the worksheet "BTC Driver Analysis".

Assumed layout:
  project_root/
    .env
    service_account.json
    scripts/
      rhodl_ratio_raw_data.py  (this file)

.env must contain:
    COINGLASS_API_KEY=...
    GOOGLE_SHEET_ID=...
    GOOGLE_SERVICE_ACCOUNT=service_account.json   # relative to project root, or absolute

Usage:
    python scripts/rhodl_ratio_raw_data.py               # overwrite A/B (leave other columns untouched)
    python scripts/rhodl_ratio_raw_data.py --append      # append only new days into A/B
    python scripts/rhodl_ratio_raw_data.py --outfile path/to/file.json
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Any
from pathlib import Path

import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

API_URL = "https://open-api-v4.coinglass.com/api/index/bitcoin-rhodl-ratio"
WORKSHEET_TITLE = "RHODL Ratio Raw Data"   # target worksheet/tab name

# --- Paths ---
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent                 # one level up
DOTENV_PATH = PROJECT_ROOT / ".env"


# ------------------ helpers ------------------ #
def load_env() -> Dict[str, str]:
    # Load .env from project root
    if not DOTENV_PATH.exists():
        sys.exit(f"ERROR: .env not found at {DOTENV_PATH}")
    load_dotenv(dotenv_path=str(DOTENV_PATH))

    key = os.getenv("COINGLASS_API_KEY")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sa_file_cfg = os.getenv("GOOGLE_SERVICE_ACCOUNT")  # absolute or relative to project root

    missing = [n for n, v in [
        ("COINGLASS_API_KEY", key),
        ("GOOGLE_SHEET_ID", sheet_id),
        ("GOOGLE_SERVICE_ACCOUNT", sa_file_cfg),
    ] if not v]
    if missing:
        sys.exit(f"ERROR: Missing in .env -> {', '.join(missing)}")

    # Resolve service account path
    sa_path = Path(sa_file_cfg)
    if not sa_path.is_absolute():
        sa_path = PROJECT_ROOT / sa_path
    if not sa_path.exists():
        sys.exit(f"ERROR: Service account JSON not found at {sa_path}")

    return {"api_key": key, "sheet_id": sheet_id, "sa_file": str(sa_path)}


def fetch_rhodl_json(api_key: str, max_retries: int = 3, timeout: int = 30) -> Dict[str, Any]:
    headers = {
        "accept": "application/json",
        "CG-API-KEY": api_key,
        "User-Agent": "rhodl-fetch/1.0",
    }
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(API_URL, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(1.5 * attempt)
    raise SystemExit(f"ERROR: API request failed after {max_retries} attempts: {last_err}")


def normalize(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Map API rows to {date, rhodl_ratio, price, timestamp_ms}; sort & dedup (full history).
    Uses timezone-aware UTC to avoid naive-datetime warnings.
    """
    out: List[Dict[str, Any]] = []
    for row in records:
        ts_ms = int(row["timestamp"])
        date_utc = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
        out.append({
            "date": date_utc.isoformat(),
            "rhodl_ratio": float(row["rhodl_ratio"]),
            "price": float(row.get("price", 0.0)),
            "timestamp_ms": ts_ms,
        })
    out.sort(key=lambda x: x["date"])
    # dedup by date (keep last occurrence)
    return list({rec["date"]: rec for rec in out}.values())


def save_json(path: Path, data: List[Dict[str, Any]]) -> None:
    # Ensure parent directory exists (creates ./json_data/ automatically)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def google_client(sa_file: str) -> gspread.Client:
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(sa_file, scope)
    return gspread.authorize(creds)


def open_target_worksheet(client: gspread.Client, sheet_id: str) -> gspread.Worksheet:
    ss = client.open_by_key(sheet_id)
    try:
        return ss.worksheet(WORKSHEET_TITLE)
    except gspread.WorksheetNotFound:
        # Create it if missing; put headers in A1:B1
        ws = ss.add_worksheet(title=WORKSHEET_TITLE, rows=1000, cols=26)
        ws.update(range_name="A1:B1", values=[["Date", "RHODL Ratio"]])
        return ws


def write_cols_ab_overwrite(ws: gspread.Worksheet, records: List[Dict[str, Any]]) -> None:
    """Replace ONLY columns A & B with header + data; leave other columns intact."""
    rows = [["Date", "RHODL Ratio"]]
    rows.extend([[r["date"], r["rhodl_ratio"]] for r in records])

    # Clear only A:B, leave other columns intact
    try:
        ws.batch_clear(["A:B"])  # gspread ≥5.x
    except AttributeError:
        # Fallback for older gspread: clear values in A:B via batch_update
        ws.spreadsheet.batch_update({
            "requests": [{
                "updateCells": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "startColumnIndex": 0,  # A
                        "endColumnIndex": 2     # up to (not including) C
                    },
                    "fields": "userEnteredValue"
                }
            }]
        })

    end_row = len(rows)
    ws.update(range_name=f"A1:B{end_row}", values=rows, value_input_option="RAW")


def append_only_cols_ab(ws: gspread.Worksheet, records: List[Dict[str, Any]]) -> int:
    """Append missing dates (A/B only). Does not touch other columns."""
    existing = ws.col_values(1)  # Column A (Date)
    if not existing:
        # If empty sheet, ensure header exists before appending
        ws.update(range_name="A1:B1", values=[["Date", "RHODL Ratio"]])
        existing_dates = set()
    else:
        # Skip header if present
        existing_dates = set(x for x in existing[1:] if x)

    new_rows = [[r["date"], r["rhodl_ratio"]] for r in records if r["date"] not in existing_dates]
    if new_rows:
        ws.append_rows(new_rows, value_input_option="RAW")
    return len(new_rows)


# ------------------ main ------------------ #
def main():
    parser = argparse.ArgumentParser(description="Fetch RHODL and write to 'BTC Driver Analysis' A/B columns.")
    parser.add_argument("--append", action="store_true", help="Append only new days into columns A/B.")
    parser.add_argument(
        "--outfile",
        default=str(Path("json_data") / "rhodl_daily.json"),
        help="Path to save rhodl JSON (default: ./json_data/rhodl_daily.json)."
    )
    args = parser.parse_args()

    cfg = load_env()

    raw = fetch_rhodl_json(cfg["api_key"])
    if not isinstance(raw, dict) or "data" not in raw:
        sys.exit(f"Unexpected API response shape: {str(raw)[:200]} ...")

    records = normalize(raw["data"])

    # Save JSON (ensures folder exists)
    save_json(Path(args.outfile), records)
    print(f"💾 Saved {len(records)} rows to {args.outfile}")

    client = google_client(cfg["sa_file"])
    ws = open_target_worksheet(client, cfg["sheet_id"])

    if args.append:
        added = append_only_cols_ab(ws, records)
        print(f"📈 Append mode: added {added} new rows to worksheet '{WORKSHEET_TITLE}' (A/B only)")
    else:
        write_cols_ab_overwrite(ws, records)
        print(f"✅ Overwrote columns A/B in worksheet '{WORKSHEET_TITLE}' with {len(records)} rows")


if __name__ == "__main__":
    main()

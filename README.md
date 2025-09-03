# RHODL Ratio to Google Sheets

This project fetches **Bitcoin RHODL Ratio** data from the [CoinGlass
API](https://docs.coinglass.com) and uploads it directly to a Google
Sheet.

## Features

-   Fetches daily RHODL Ratio values from CoinGlass (requires API key)
-   Filters data from **2012-01-01** onward (ignores noisy early years)
-   Saves results locally as `rhodl_daily.json`
-   Uploads to Google Sheets using a Service Account
-   Two modes:
    -   **Rewrite**: clears and replaces the entire sheet
    -   **Append**: only appends new daily rows

## Requirements

-   Python 3.8+
-   CoinGlass API key (Startup tier or above)
-   Google Cloud Service Account with Sheets API enabled
-   Google Sheet shared with your Service Account email

## Installation

``` bash
git clone <your-repo-url>
cd rhodl-to-sheets
pip install -r requirements.txt
```

### Dependencies

    requests
    gspread
    oauth2client
    python-dotenv

## Setup

1.  **Environment Variables**\
    Create a `.env` file in the project root:

```{=html}
<!-- -->
```
    COINGLASS_API_KEY=your_coinglass_api_key
    GOOGLE_SHEET_ID=your_google_sheet_id
    GOOGLE_SERVICE_ACCOUNT=service_account.json

-   `COINGLASS_API_KEY`: Your CoinGlass API key\
-   `GOOGLE_SHEET_ID`: Found in the Google Sheet URL\
-   `GOOGLE_SERVICE_ACCOUNT`: Filename of your service account JSON key

2.  **Google Sheets API**\

-   Enable the Sheets API in [Google Cloud
    Console](https://console.cloud.google.com/)\
-   Create a Service Account and download the JSON key\
-   Share your Google Sheet with the Service Account email

## Usage

### Rewrite the entire sheet

``` bash
python app.py
```

### Append only new rows

``` bash
python app.py --append
```

## Output

-   Local file: `rhodl_daily.json`
-   Google Sheet:
    -   Column A → Dates\
    -   Column B → RHODL Ratio values

## Notes

-   RHODL data before 2012 is noisy due to lack of older coins, so it's
    filtered out by default.\
-   Script can be scheduled with cron (Linux/macOS) or Task Scheduler
    (Windows) for daily updates.

------------------------------------------------------------------------

🚀 Built to simplify tracking the Bitcoin RHODL Ratio in Google Sheets!

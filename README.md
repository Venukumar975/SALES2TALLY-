# Sales & Purchase Registers Automation Suite - Codebase & Route Documentation

## Table of Contents
1. [Overview & Architecture](#overview--architecture)
2. [Dependencies & Imports](#dependencies--imports)
   - [Python (`app.py`)](#python-apppy)
   - [Frontend (`templates/index.html` & `static/style.css`)](#frontend-templatesindexhtml--staticstylecss)
3. [Backend Route Reference (`app.py`)](#backend-route-reference-apppy)
   - [Navigation & Core File Handling](#1-navigation--core-file-handling)
   - [Header, Date & Tax Rate Detection](#2-header-date--tax-rate-detection)
   - [Tally Prime Synchronization & Cache](#3-tally-prime-synchronization--cache)
   - [Party & Product Verification](#4-party--product-verification)
   - [Master Creation in Tally](#5-master-creation-in-tally)
   - [Generation & Downloads](#6-generation--downloads)
4. [Helper Functions & Business Logic (`app.py`)](#helper-functions--business-logic-apppy)
5. [Frontend UI & Client-Side Logic (`templates/index.html`)](#frontend-ui--client-side-logic-templatesindexhtml)
   - [Step-by-Step UI Layout](#step-by-step-ui-layout)
   - [Modals](#modals)
   - [Client-Side JavaScript Route Handling & Functions](#client-side-javascript-route-handling--functions)
6. [Data Flow & Integration Lifecycle](#data-flow--integration-lifecycle)
7. [Tally Prime XML Specs](#tally-prime-xml-specs)

---

## Overview & Architecture

The **Sales & Purchase Registers Automation Suite** is a desktop-grade web application built with **Python (Flask)** and modern **Vanilla HTML5/CSS3/JavaScript**. It bridges arbitrary supplier or sales spreadsheets (.xlsx, .xls) with **Tally Prime** via its XML HTTP Interface (`http://localhost:9000`).

### Key Capabilities:
- **Header Mapping**: Map any custom Excel headers to 14 standardized accounting fields with automatic fuzzy keyword matching.
- **Date Slicing**: Slices and filters transactions by date range before processing.
- **Tally Prime Cache & Sync**: Syncs ledger lists (Sundry Debtors) and stock items (Inventory) directly from Tally Prime into local JSON cache folders (`tally_companies/<company_name>/`).
- **Master Verification & Creation**: Performs exact and tokenized Jaccard similarity fuzzy-matching on customer names and products; allows 1-click automatic creation of missing Sundry Debtors and Stock Items directly into Tally Prime via XML requests.
- **Tally XML Generation**: Compiles multi-item invoices into standard Tally `Voucher` XML envelopes with exact commercial rounding and automatic `Misc` (round-off) ledger offsets.
- **Formatted Excel Report**: Creates a dual-sheet formatted workbook containing clean processed rows and an aesthetic grouped summary using `XlsxWriter`.

---

## Dependencies & Imports

### Python (`app.py`)

| Module / Package | Purpose |
| :--- | :--- |
| `sys` | Detects PyInstaller standalone executable environment (`sys.frozen`, `sys._MEIPASS`, `sys.executable`). |
| `os` | Handles filesystem operations, directory paths, cache folders, and uploads. |
| `re` | Regex pattern matching for cleaning company names, party tokenization, and XML entity sanitizer. |
| `uuid` | Generates unique session IDs for uploaded spreadsheet files (`uuid.uuid4()`). |
| `math` | Used for commercial half-up rounding calculations (`math.floor`, `math.ceil`). |
| `requests` | Sends synchronous HTTP POST requests with XML payloads to Tally Prime running at `http://localhost:9000`. |
| `json` | Reads and writes cached Tally company ledgers and stock items in JSON format. |
| `xml.etree.ElementTree as ET` | Parses XML responses received from Tally Prime (import status, errors, collections). |
| `xml.sax.saxutils.escape as xml_escape` | Escapes special XML characters (`&`, `<`, `>`, `"`, `'`) for safe payload interpolation. |
| `datetime` | Parsing, formatting, and timestamping sync records and invoice transaction dates. |
| `pandas as pd` | High-performance Excel reading (`pd.ExcelFile`, `pd.read_excel`), filtering, dataframe manipulation, and Excel export with `pd.ExcelWriter`. |
| `flask` (`Flask`, `request`, `jsonify`, `render_template`, `send_from_directory`) | Micro-web framework powering routing, API responses, template rendering, and file downloads. |
| `webbrowser`, `threading.Timer` | Automatically opens the browser to `http://localhost:5005` 1.5 seconds after the server boots. |

### Frontend (`templates/index.html` & `static/style.css`)

| Resource | Purpose |
| :--- | :--- |
| **Google Fonts** (`Outfit`, `Inter`) | Modern typography for interface headers and data tables. |
| `static/style.css` | Complete custom dark-theme responsive design system, loaders, modals, badges, dropzones, and select elements. |
| **Vanilla JS (ES6+)** | Native `fetch` API for async server communication, DOM manipulation, auto-matching, and modal management. |

---

## Backend Route Reference (`app.py`)

Below is the exhaustive list of all 16 Flask routes implemented in `app.py`.

### 1. Navigation & Core File Handling

#### `GET /`
- **Handler**: `index()` (line 519)
- **Purpose**: Serves the main single-page application interface.
- **Returns**: Rendered `templates/index.html`.

#### `POST /upload`
- **Handler**: `upload()` (line 523)
- **Purpose**: Receives the user's uploaded `.xlsx` or `.xls` file and extracts available worksheet names.
- **Request**: Multipart Form Data with file field `excel_file`.
- **Logic**:
  1. Validates extension (`.xlsx`, `.xls`).
  2. Generates a random `uuid.uuid4()` as `file_id`.
  3. Saves file to `uploads/<file_id><ext>`.
  4. Reads worksheet names using `pd.ExcelFile(file_path).sheet_names`.
- **Response**:
  ```json
  {
    "success": true,
    "file_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "sheets": ["Sales Register", "Sheet1"]
  }
  ```

#### `POST /get-headers`
- **Handler**: `get_headers()` (line 550)
- **Purpose**: Reads column headers from the selected worksheet starting from a specified header row.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "header_row": 1
  }
  ```
- **Logic**:
  1. Locates uploaded file in `uploads/`.
  2. Calls `find_headers_and_df(file_path, sheet_name, header_row)`.
  3. Resolves and deduplicates blank or duplicate column names (`Unnamed_Col_0`, etc.).
- **Response**:
  ```json
  {
    "success": true,
    "headers": ["Date", "Invoice No", "Customer", "GSTIN", "State", "Item", "HSN", "Qty", "Taxable", "CGST", "SGST", "IGST", "Total", "Unit"]
  }
  ```

---

### 2. Header, Date & Tax Rate Detection

#### `POST /api/get-date-range`
- **Handler**: `get_date_range()` (line 580)
- **Purpose**: Scans the mapped date column to determine minimum and maximum transaction dates for date range filtering.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "date_col": "Invoice Date",
    "header_row": 1
  }
  ```
- **Logic**: Parses all non-empty dates in `date_col` using `parse_date_to_comparable()`, finds `min()` and `max()`, and formats as `YYYY-MM-DD`.
- **Response**:
  ```json
  {
    "success": true,
    "min_date": "2024-04-01",
    "max_date": "2024-04-30"
  }
  ```

#### `POST /api/detect-tax-rates`
- **Handler**: `detect_tax_rates()` (line 622)
- **Purpose**: Automatically analyzes the spreadsheet data to calculate effective GST percentages present across rows.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "mappings": {
      "Taxable Amount": "Taxable Value",
      "CGST Amount": "CGST",
      "SGST Amount": "SGST",
      "IGST Amount": "IGST"
    },
    "header_row": 1
  }
  ```
- **Logic**: Iterates over rows with `taxable > 0`; calculates `round((tax / taxable) * 100)` for CGST, SGST, IGST; accumulates keys like `CGST Output 9%`, `SGST Output 9%`, `IGST Output 18%`.
- **Response**:
  ```json
  {
    "success": true,
    "tax_keys": ["CGST Output 9%", "IGST Output 18%", "SGST Output 9%"]
  }
  ```

---

### 3. Tally Prime Synchronization & Cache

#### `POST /api/tally/sync`
- **Handler**: `api_tally_sync()` (line 271)
- **Purpose**: Connects to Tally Prime on `localhost:9000` to export all Ledgers (Sundry Debtors, Sales, Tax ledgers) and caches them in JSON.
- **Request Body (JSON)**:
  ```json
  {
    "company_name": "ABC Enterprises Pvt Ltd"
  }
  ```
- **Logic**:
  1. Posts XML collection export request (`<TYPE>Collection</TYPE><ID>Ledger</ID>`) to `http://localhost:9000`.
  2. Cleans non-printable XML entities via regex.
  3. Parses `<LEDGER NAME="...">` and `<NAME>...</NAME>` nodes.
  4. Saves to `tally_companies/<safe_company_name>/tally_ledger_cache.json`.
- **Response**:
  ```json
  {
    "success": true,
    "count": 450,
    "company_name": "ABC Enterprises Pvt Ltd"
  }
  ```

#### `POST /api/tally/sync-stock`
- **Handler**: `api_tally_sync_stock()` (line 434)
- **Purpose**: Connects to Tally Prime on `localhost:9000` to export all Stock Items (Inventory) and caches them in JSON.
- **Request Body (JSON)**:
  ```json
  {
    "company_name": "ABC Enterprises Pvt Ltd"
  }
  ```
- **Logic**:
  1. Posts XML collection export request (`<TYPE>Collection</TYPE><ID>StockItem</ID>`) to `http://localhost:9000`.
  2. Cleans non-printable XML entities.
  3. Parses `<STOCKITEM NAME="...">` and `<NAME>...</NAME>` nodes.
  4. Saves to `tally_companies/<safe_company_name>/tally_stock_cache.json`.
- **Response**:
  ```json
  {
    "success": true,
    "count": 120,
    "company_name": "ABC Enterprises Pvt Ltd"
  }
  ```

#### `GET /api/tally/companies`
- **Handler**: `api_tally_companies()` (line 356)
- **Purpose**: Lists all locally cached Tally companies, last sync timestamps, and counts of ledgers and stock items.
- **Response**:
  ```json
  {
    "success": true,
    "companies": [
      {
        "safe_name": "ABC Enterprises Pvt Ltd",
        "display_name": "ABC Enterprises Pvt Ltd",
        "ledger_last_sync": "2024-04-15 10:30:00",
        "stock_last_sync": "2024-04-15 10:31:00",
        "has_ledgers": true,
        "has_stock": true,
        "ledger_count": 450,
        "stock_count": 120
      }
    ]
  }
  ```

#### `POST /api/tally/ledgers`
- **Handler**: `get_tally_ledgers()` (line 415)
- **Purpose**: Fetches the list of cached ledgers for a given company.
- **Request Body (JSON)**:
  ```json
  {
    "company_name": "ABC Enterprises Pvt Ltd"
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "ledgers": ["Cash", "Goods Sales", "CGST Output 9%", "SGST Output 9%", "XYZ Corp"]
  }
  ```

---

### 4. Party & Product Verification

#### `POST /api/check-parties`
- **Handler**: `check_parties()` (line 738)
- **Purpose**: Compares party names from the spreadsheet against cached Tally ledgers to classify them into Exact Matches, Fuzzy Similar Matches, or Missing Ledgers.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "mappings": { ... },
    "ledger_company": "ABC Enterprises Pvt Ltd",
    "from_date": "2024-04-01",
    "to_date": "2024-04-30",
    "header_row": 1
  }
  ```
- **Matching Algorithm**:
  1. *Exact match* (case-insensitive).
  2. *Compact match* (ignoring punctuation/spaces like "YG" vs "Y G").
  3. *Suffix-cleaned match* (stripping "pvt", "ltd", "co", "llp").
  4. *Tokenized Jaccard similarity* (threshold >= 0.60).
- **Response**:
  ```json
  {
    "success": true,
    "perfect_matches": ["XYZ Private Limited"],
    "similar_matches": [
      {
        "original": "Acme Corp Ltd",
        "matched": "Acme Corp",
        "score": 85
      }
    ],
    "non_existing": [
      {
        "name": "New Client Enterprises",
        "state": "Andhra Pradesh",
        "gstin": "37AAAAA0000A1Z5"
      }
    ]
  }
  ```

#### `POST /api/check-products`
- **Handler**: `check_products()` (line 859)
- **Purpose**: Compares Excel product descriptions against cached Tally stock items.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "mappings": { ... },
    "stock_company": "ABC Enterprises Pvt Ltd",
    "from_date": "2024-04-01",
    "to_date": "2024-04-30",
    "header_row": 1
  }
  ```
- **Response**:
  ```json
  {
    "success": true,
    "perfect_matches": ["Widget A 100mm"],
    "non_existing": ["New Product Pro Max"]
  }
  ```

---

### 5. Master Creation in Tally

#### `POST /api/tally/create-missing-ledgers`
- **Handler**: `create_missing_ledgers()` (line 932)
- **Purpose**: Generates Tally `All Masters` XML payload for missing party ledgers (under `Sundry Debtors`) and directly imports them into Tally Prime via HTTP POST.
- **Request Body (JSON)**:
  ```json
  {
    "ledger_company": "ABC Enterprises Pvt Ltd",
    "parties": [
      {
        "name": "New Client Enterprises",
        "state": "Andhra Pradesh",
        "gstin": "37AAAAA0000A1Z5"
      }
    ]
  }
  ```
- **Logic**:
  1. Normalizes party names (replaces `&` with `and`, removes special symbols).
  2. Sets `GSTREGISTRATIONTYPE` (`Regular` if GSTIN present, else `Unregistered`).
  3. Posts envelope to `http://localhost:9000`.
  4. Parses `<CREATED>`, `<ERRORS>`, `<EXCEPTIONS>` from Tally response.
  5. Auto-triggers a resync of the ledger cache.
- **Response**:
  ```json
  {
    "success": true,
    "created_count": 1
  }
  ```

#### `POST /api/tally/create-missing-items`
- **Handler**: `create_missing_items()` (line 1118)
- **Purpose**: Generates Tally `All Masters` XML payload for missing inventory stock items and imports them into Tally Prime.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "mappings": { ... },
    "header_row": 1,
    "company_name": "ABC Enterprises Pvt Ltd",
    "under": "Primary",
    "units": "Nos",
    "supply_type": "Goods",
    "products": ["New Product Pro Max"]
  }
  ```
- **Logic**:
  1. Finds the product row in the spreadsheet to retrieve HSN Code and GST rate.
  2. Generates `<STOCKITEM>` with `BASEUNITS`, `GSTAPPLICABLE`, `GSTTYPEOFSUPPLY`, `HSNDETAILS.LIST`, and `GSTDETAILS.LIST`.
  3. Posts envelope to `http://localhost:9000`.
  4. Auto-resyncs stock items cache.
- **Response**:
  ```json
  {
    "success": true,
    "created_count": 1,
    "ignored_count": 0
  }
  ```

---

### 6. Generation & Downloads

#### `POST /generate`
- **Handler**: `generate()` (line 1392)
- **Purpose**: Generates complete Tally `Vouchers` import XML with multi-item grouped invoices, mapped tax ledger accounts, and round-off offset calculation.
- **Request Body (JSON)**:
  ```json
  {
    "file_id": "...",
    "sheet_name": "Sales Register",
    "mappings": { ... },
    "original_filename": "Sales_April.xlsx",
    "ledger_company": "ABC Enterprises Pvt Ltd",
    "xml_company_name": "ABC Enterprises Pvt Ltd",
    "sales_ledger_name": "Goods Sales",
    "misc_ledger_name": "Misc Expenses",
    "from_date": "2024-04-01",
    "to_date": "2024-04-30",
    "header_row": 1,
    "tax_ledger_mappings": {
      "CGST Output 9%": "CGST Output 9%",
      "SGST Output 9%": "SGST Output 9%"
    }
  }
  ```
- **Calculation Logic**:
  1. Groups rows by `Invoice No`.
  2. For each invoice, builds `<ALLINVENTORYENTRIES.LIST>` for each product with `RATE`, `AMOUNT`, `ACTUALQTY`, `BILLEDQTY`, and accounting allocation to `sales_ledger_name`.
  3. Groups tax entries by rate percentage and sums them.
  4. Computes `exact_credits_sum = taxable_total + cgst_total + sgst_total + igst_total`.
  5. Computes `rounded_total = custom_round(total_invoice_amount)`.
  6. Calculates `roundoff_offset = round(rounded_total - exact_credits_sum, 2)` and adds a `Misc` ledger entry if non-zero.
  7. Adds the party debit entry with `-rounded_total`.
  8. Saves XML file to `processed/<original_filename>_vouchers.xml`.
- **Response**:
  ```json
  {
    "success": true,
    "filename": "Sales_April_vouchers.xml",
    "row_count": 150
  }
  ```

#### `GET /download/<path:filename>`
- **Handler**: `download(filename)` (line 1723)
- **Purpose**: Serves generated XML or Excel files from the `processed/` folder as downloadable attachments.
- **Returns**: File download attachment.

#### `POST /generate_excel`
- **Handler**: `generate_excel()` (line 1740)
- **Purpose**: Generates a professionally styled `.xlsx` workbook using `xlsxwriter` containing two sheets:
  1. **"Processed Data"**: Flat mapped records with inserted `Misc` and `Invoice Rounded Total` columns.
  2. **"Final Summary & Grouping"**: Visual grouped invoice layout with highlighted invoice header bars, itemized line rows, per-invoice subtotals with inline tax percentages, 3 spacer rows between invoices, and a Grand Total Debits summary.
- **Request Body (JSON)**: Same parameters as `/generate` (minus Tally XML company name).
- **Response**:
  ```json
  {
    "success": true,
    "filename": "Sales_April_processed.xlsx",
    "row_count": 150
  }
  ```

---

## Helper Functions & Business Logic (`app.py`)

| Function | Line | Purpose |
| :--- | :--- | :--- |
| `get_tally_cache_folder()` | 37 | Returns / creates the `tally_companies/` directory beside the application. |
| `find_headers_and_df(file_path, sheet_name, header_row)` | 60 | Reads Excel at 1-based header index; cleans duplicate & blank column names. |
| `clean_gst_cell(v)` | 109 | Cleans GSTIN values; strips `nan`, `none`, `0`, `0.0`. |
| `clean_date_cell(v)` | 117 | Parses various date formats (`%d-%m-%Y`, `%d/%m/%Y`, `%Y-%m-%d`, `%d-%b-%y`, etc.) to standard `DD-MM-YYYY` string. |
| `parse_date_to_comparable(v)` | 135 | Converts cell values to a Python `datetime.date` object for comparison and range filtering. |
| `filter_df_by_date_range(df_data, mappings, from_date_str, to_date_str)` | 158 | Filters dataframe rows within inclusive from/to date strings. |
| `clean_numeric_cell(v)` | 194 | Strips commas and formats numeric numbers as integer or float. |
| `clean_text_cell(v)` | 208 | Strips strings and removes `.0` suffix from integer strings (e.g. HSN codes). |
| `escape_xml_value(value)` | 219 | Escapes characters for XML attribute and text safety. |
| `normalize_party_name(value)` | 225 | Replaces symbols (`&` -> `and`, `+` -> `plus`), strips non-alphanumeric chars. |
| `clean_and_tokenize(name)` | 244 | Tokenizes party strings and removes legal suffixes (`pvt`, `ltd`, `llp`, `co`). |
| `get_word_match_score(name1, name2)` | 256 | Computes Jaccard word-token intersection over union score. |
| `compact_party_name(name)` | 265 | Strips all spaces and symbols to compare spacing differences. |
| `find_matching_ledger(excel_party, tally_ledgers)` | 692 | Multi-stage fuzzy matcher selecting the best ledger match. |
| `infer_ledger(tally_ledgers, tax_type, rate, fallback)` | 1376 | Helper to infer matching tax ledgers. |
| `custom_round(val)` | 1727 | Commercial half-up rounding (`val - floor(val) >= 0.5 ? ceil : floor`). |

---

## Frontend UI & Client-Side Logic (`templates/index.html`)

### Step-by-Step UI Layout

1. **Card 1: Source Excel File & Worksheet** (`#card-excel`)
   - Interactive drag-and-drop dropzone or file picker (`#excel_file`).
   - Displays uploaded file info tag with reset button.
   - Dynamic worksheet selection dropdown (`#sheet_select`) and Header Row index input (`#header_row`).
2. **Card 2: Map Column Headers** (`#card-mapping`)
   - Standardized 14 target column grid with required/optional badges and auto-mapping status indicators.
   - Auto-Match trigger button (`triggerAutoMatch()`).
   - Optional Date Filter Slicer (`#date-slicer-container`) with `#filter-from-date` and `#filter-to-date`.
3. **Card 3: Tally Prime Sync & Import** (`#card-tally`)
   - Ledger Names Sync Box with company profile dropdown (`#tally_ledger_company_select`) and sync button.
   - Item Stock Sync Box with company profile dropdown (`#tally_stock_company_select`) and sync button.
4. **Card 4: Party Ledger Verification & Sales XML** (`#card-generate`)
   - Dual verification action buttons: **Check Party Names** and **Check Product Names**.
   - Verification Report containers (Perfect matches, Fuzzy similar matches, Non-existing masters table).
   - Voucher Ledger Accounts configuration (`#xml_company_name`, `#sales_ledger_select`, `#misc_ledger_select`).
   - Dynamic Detected Tax Types & Rates mapping grid (`#detected-tax-rates-container`).
   - Creation and export buttons:
     - `Create Party Names Ledgers in Tally` (`#btn-create-tally-ledgers`)
     - `Create Stock Items in Tally` (`#btn-create-tally-items`)
     - `Generate Sales Register XML` (`#btn-generate-xml`)
     - `Generate Processed Excel` (`#btn-generate-excel`)

### Modals

- **Sync Ledgers Modal** (`#sync-ledgers-modal`): Prompts company name and triggers `/api/tally/sync`.
- **Sync Stock Modal** (`#sync-stock-modal`): Prompts company name and triggers `/api/tally/sync-stock`.
- **Create Missing Stock Items Modal** (`#create-stock-items-modal`): Allows setting `Stock Group (Under)`, `Unit of Measure (Units)`, and `Type of Supply` before posting missing items to Tally.

---

### Client-Side JavaScript Route Handling & Functions

| JS Function | Invoked Backend Route | Description |
| :--- | :--- | :--- |
| `uploadFile(file)` | `POST /upload` | Uploads selected spreadsheet and populates sheet list. |
| `analyzeSheet(sheet)` | `POST /get-headers` | Reads headers for chosen sheet and builds the mapping grid. |
| `updateDateSlicerLimits()` | `POST /api/get-date-range` | Updates min/max dates on date slicer inputs when `Invoice Date` is mapped. |
| `detectAndRenderTaxRates()` | `POST /api/detect-tax-rates` | Detects tax percentages and dynamically generates tax ledger dropdowns. |
| `loadSyncedCompanies()` | `GET /api/tally/companies` | Fetches cached companies and populates ledger and stock profile dropdowns. |
| `loadLedgersForVoucherConfig(co)` | `POST /api/tally/ledgers` | Loads ledgers to pre-fill Sales, Misc, and Tax dropdowns. |
| `syncTally(type)` | `POST /api/tally/sync` or `/api/tally/sync-stock` | Triggers Tally export and updates local cache. |
| `checkPartyNames()` | `POST /api/check-parties` | Verifies Excel customer names against Tally ledgers. |
| `checkProductNames()` | `POST /api/check-products` | Verifies Excel products against Tally stock items. |
| `createTallyLedgers()` | `POST /api/tally/create-missing-ledgers` | Directly imports missing customer ledgers into Tally. |
| `submitCreateStockItems()` | `POST /api/tally/create-missing-items` | Directly imports missing stock items into Tally. |
| `generateSalesXML()` | `POST /generate` | Generates and exposes the Tally Vouchers XML download link. |
| `generateProcessedExcel()` | `POST /generate_excel` | Generates and exposes the processed Excel workbook download link. |

---

## Data Flow & Integration Lifecycle

```
[ Excel File (.xlsx / .xls) ]
              │
              ▼  POST /upload
      [ Select Worksheet & Header Row ]
              │
              ▼  POST /get-headers
     [ 14 Target Fields Auto-Mapped ]
              │
              ▼  GET /api/tally/companies & POST /api/tally/sync
   [ Tally Prime Local Cache (Ledgers & Stock) ]
              │
              ├──────────────────────────────────┐
              ▼ POST /api/check-parties          ▼ POST /api/check-products
     [ Party Verification Report ]       [ Product Verification Report ]
              │                                  │
     (If Missing Ledgers)               (If Missing Stock Items)
              ▼                                  ▼
 POST /api/tally/create-missing-ledgers  POST /api/tally/create-missing-items
              │                                  │
              └─────────────────┬────────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼ POST /generate                    ▼ POST /generate_excel
   [ Tally Vouchers XML ]              [ 2-Sheet Formatted Excel ]
  (Ready for Tally Import)              (Summary & Grouped Rows)
```

---

## Tally Prime XML Specs

- **Tally Endpoint**: `http://localhost:9000`
- **Collection Export Envelope**: Requests `<TYPE>Collection</TYPE>` with `<ID>Ledger</ID>` or `<ID>StockItem</ID>`.
- **Master Import Envelope**: Sent with `<REPORTNAME>All Masters</REPORTNAME>` and `<SVCURRENTCOMPANY>`.
- **Vouchers Import Envelope**: Sent with `<REPORTNAME>Vouchers</REPORTNAME>`, `<VOUCHER VCHTYPE="Sales">`, itemized inventory blocks, tax ledger credits, and balanced party debits.

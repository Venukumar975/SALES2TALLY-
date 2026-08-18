# Sales & Purchase Registers Automation Suite - Codebase & Architecture Guide

## Table of Contents
1. [Overview & Modular Architecture](#overview--modular-architecture)
2. [Directory & File Organization](#directory--file-organization)
3. [Modules Breakdown](#modules-breakdown)
   - [Core Configuration & Entry Point](#core-configuration--entry-point)
   - [Utils Package (`utils/`)](#utils-package-utils)
   - [Services Package (`services/`)](#services-package-services)
   - [Routes Package (`routes/`)](#routes-package-routes)
   - [Frontend Architecture (`templates/` & `static/js/`)](#frontend-architecture-templates--staticjs)
4. [Backend API Reference](#backend-api-reference)
5. [Tally Prime XML Integration Protocol & Commercial Rounding](#tally-prime-xml-integration-protocol--commercial-rounding)

---

## Overview & Modular Architecture

The **Sales & Purchase Registers Automation Suite** transforms external sales & purchase register spreadsheets (`.xlsx`, `.xls`) into **Tally Prime** XML Vouchers and formatted Excel summaries.

The codebase is fully modularized with clean isolation across configuration, utilities, external services, Flask blueprints, and client-side JavaScript components.

```
Sales & Purchase Registers/
│
├── app.py                          # Lean app entry point & server launcher (~36 lines)
├── config.py                       # Paths, constants (TARGET_COLUMNS), PyInstaller configs
│
├── utils/                          # Utility functions
│   ├── __init__.py
│   ├── helpers.py                  # Excel reading, date parsing, cell cleaners, commercial rounding
│   └── matching.py                 # Name normalization, tokenization, Jaccard fuzzy similarity
│
├── services/                       # Business logic & external integration services
│   ├── __init__.py
│   ├── tally_ledger_service.py     # Tally Prime XML HTTP communications, sync & cache ledgers
│   ├── tally_stock_service.py      # Tally Prime XML HTTP communications, sync & cache stock items
│   ├── master_creator.py           # XML builders & executors for creating missing Ledgers & Stock Items
│   ├── xml_generator.py            # Generates multi-item sales vouchers XML with exact round-off offset
│   └── excel_generator.py          # Generates 2-sheet formatted summary Excel workbook (XlsxWriter)
│
├── routes/                         # Flask API blueprints
│   ├── __init__.py
│   ├── main_routes.py              # Index (/), Upload (/upload), Headers (/get-headers), Download (/download)
│   ├── tally_routes.py             # Tally sync, companies list, ledgers retrieval, master creation endpoints
│   ├── analysis_routes.py          # Date range detection, tax rates detection, party & product verification
│   └── generator_routes.py         # /generate (XML) and /generate_excel (XLSX)
│
├── templates/
│   └── index.html                  # Pure semantic HTML markup & modal dialogs (~400 lines)
│
└── static/
    ├── style.css                   # Custom CSS styling & modal definitions
    └── js/                         # Modular Frontend JavaScript
        ├── config.js               # Field definitions (targetFields) and autoMatches keywords
        ├── utils.js                # UI status bar notifications and loaders
        ├── upload.js               # Drag-and-drop, workbook uploading, and sheet selection
        ├── mapping.js              # Header mapping grid builder, auto-match, and date slicer
        ├── tally.js                # Tally sync, company profile loading, dynamic tax rate detection
        ├── verification.js         # Party & product verification reports and missing master creation modals
        ├── generator.js            # XML & Excel generation triggers and download link handlers
        └── main.js                 # Main application entry point & DOM event wiring
```

---

## Modules Breakdown

### Core Configuration & Entry Point

| File | Purpose |
| :--- | :--- |
| [`app.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/app.py) | Application factory (`create_app`), registers all 4 modular blueprints (`main_bp`, `tally_bp`, `analysis_bp`, `generator_bp`), launches browser on port 5005. |
| [`config.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/config.py) | Base paths, PyInstaller frozen directory resolution (`_MEIPASS`), 14 target column definitions, Tally URL (`http://localhost:9000`). |

### Utils Package (`utils/`)

| Module | Key Functions | Description |
| :--- | :--- | :--- |
| [`utils/helpers.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/utils/helpers.py) | `find_headers_and_df`, `clean_gst_cell`, `clean_date_cell`, `parse_date_to_comparable`, `filter_df_by_date_range`, `clean_numeric_cell`, `clean_text_cell`, `to_float`, `custom_round` | Slices Excel sheets by header row, cleans messy data, handles date parsing and commercial half-up rounding. |
| [`utils/matching.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/utils/matching.py) | `normalize_party_name`, `clean_and_tokenize`, `get_word_match_score`, `compact_party_name`, `find_matching_ledger` | Normalizes business party names, strips suffixes (Pvt Ltd, LLP), and performs tokenized Jaccard similarity matching (>= 0.60). |

### Services Package (`services/`)

| Module | Key Functions | Description |
| :--- | :--- | :--- |
| [`services/tally_ledger_service.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/services/tally_ledger_service.py) | `sync_ledgers_from_tally`, `get_cached_ledgers`, `get_all_cached_companies`, `clean_tally_xml` | Handles HTTP XML export requests to Tally Prime on port 9000 for accounting ledgers and manages local JSON cache in `tally_companies/`. |
| [`services/tally_stock_service.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/services/tally_stock_service.py) | `sync_stock_from_tally`, `get_cached_stock` | Handles HTTP XML export requests to Tally Prime on port 9000 for inventory stock items and manages local JSON cache. |
| [`services/master_creator.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/services/master_creator.py) | `create_missing_ledgers_in_tally`, `create_missing_stock_items_in_tally`, `escape_xml_value` | Generates Tally `All Masters` XML envelopes to auto-create missing Sundry Debtors and Stock Items (with HSN & GST rates). |
| [`services/xml_generator.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/services/xml_generator.py) | `generate_tally_vouchers_xml` | Builds grouped multi-item sales vouchers XML with commercial rounding, tax allocations, and `Misc` offset calculation. |
| [`services/excel_generator.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/services/excel_generator.py) | `generate_formatted_excel` | Creates a 2-sheet formatted workbook (`Processed Data` + `Final Summary & Grouping`) using `xlsxwriter`. |

### Routes Package (`routes/`)

| Blueprint | Endpoints | Description |
| :--- | :--- | :--- |
| [`routes/main_routes.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/routes/main_routes.py) | `GET /`, `POST /upload`, `POST /get-headers`, `GET /download/<path:filename>` | Web UI rendering, workbook uploading, header retrieval, and file downloads. |
| [`routes/tally_routes.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/routes/tally_routes.py) | `POST /api/tally/sync`, `POST /api/tally/sync-stock`, `GET /api/tally/companies`, `POST /api/tally/ledgers`, `POST /api/tally/create-missing-ledgers`, `POST /api/tally/create-missing-items` | Tally sync, cached ledger/stock querying, and 1-click master creation. |
| [`routes/analysis_routes.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/routes/analysis_routes.py) | `POST /api/get-date-range`, `POST /api/detect-tax-rates`, `POST /api/check-parties`, `POST /api/check-products` | Date range limits, auto tax rate calculation, party verification, and product verification. |
| [`routes/generator_routes.py`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/routes/generator_routes.py) | `POST /generate`, `POST /generate_excel` | Generates Tally Vouchers XML and formatted summary Excel workbooks. |

### Frontend Architecture (`templates/` & `static/js/`)

| Script | Purpose |
| :--- | :--- |
| [`static/js/config.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/config.js) | Standard 14 target fields metadata, auto-match keywords dictionary, and shared application state. |
| [`static/js/utils.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/utils.js) | `showStatus()`, `hideStatus()` status bar notification & spinner controls. |
| [`static/js/upload.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/upload.js) | File drag-and-drop, upload request handling, and worksheet header scanning. |
| [`static/js/mapping.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/mapping.js) | Dynamic mapping grid rendering, auto-match trigger, and date slicer min/max limits. |
| [`static/js/tally.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/tally.js) | Synced company profiles loader, Tally sync triggers, and dynamic tax rate dropdown generation. |
| [`static/js/verification.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/verification.js) | Customer party and product verification reports, missing item creation modal submissions. |
| [`static/js/generator.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/generator.js) | Sales XML and Processed Excel generation requests and download link presentation. |
| [`static/js/main.js`](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/static/js/main.js) | DOMContentLoaded initialization, event listeners, and modal open/close wiring. |

---

## 6. Master Creation XML Specification Guide

For complete technical specifications, exact XML tags, and field mappings for **Party Ledgers** and **Stock Items** in Tally Prime, see the dedicated reference guide:

👉 **[TALLY_MASTER_MAPPING.md](file:///c:/Users/pichi/Desktop/Sales%20&%20Purchase%20Registers/TALLY_MASTER_MAPPING.md)**


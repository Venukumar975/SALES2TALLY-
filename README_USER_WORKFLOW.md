# SALES2TALLY - Complete User Workflow & Excel Preparation Guide

This comprehensive guide covers everything required to successfully convert sales registers from Microsoft Excel into Tally Prime XML transactions without import rejections or GSTR-1 mismatches.

---

## 📌 Table of Contents
1. [Pre-Upload Checklist & Excel Rules](#1-pre-upload-checklist--excel-rules)
2. [Step-by-Step Application Workflow](#2-step-by-step-application-workflow)
   - [Step 1: Source Excel Workbook](#step-1-source-excel-workbook)
   - [Step 2: Map Column Headers](#step-2-map-column-headers)
   - [Step 3: Tally Prime Integration & Sync](#step-3-tally-prime-integration--sync)
   - [Step 4: Master Verification Hub](#step-4-master-verification-hub)
   - [Step 5: Tax Types & Export Hub](#step-5-tax-types--export-hub)
3. [Impact of Missing, Empty, or Misconfigured Values](#3-impact-of-missing-empty-or-misconfigured-values)
4. [Tally Prime XML Import Instructions](#4-tally-prime-xml-import-instructions)

---

## 1. Pre-Upload Checklist & Excel Rules

Before uploading your file into the application, verify that your workbook adheres to the following rules:

### A. The 14 Standard Columns

| Column Name | Expected Format | Critical Purpose |
| :--- | :--- | :--- |
| **`Invoice Date`** | Date (`YYYY-MM-DD` or `DD-MM-YYYY`) | Voucher date. Used for chronological ordering and date range slicing. |
| **`Invoice No`** | Text / Alphanumeric | Groups multi-line product rows into a single Tally sales invoice. |
| **`Party Name`** | Text | Customer/Debtor account name. Auto-linked to Tally Sundry Debtors. |
| **`GST no`** | 15-char GSTIN or Blank | Party GSTIN. If blank, registered as `Unregistered/Consumer`. |
| **`State Name`** | Official State Name | **Must be an official State name** (e.g. `Telangana`, `Andhra Pradesh`). Never use city names (e.g. `Hyderabad`). |
| **`Product`** | Text | Product description. Auto-linked to Tally Stock Items. |
| **`HSN Code`** | Numeric / Text (4–8 digits) | Product HSN/SAC code. |
| **`Qty`** | Numeric ($\ge 0$) | Quantity billed. |
| **`UOM`** | Text (e.g., `Nos`, `Pcs`, `Kgs`) | **Must exist in Tally Masters** before voucher import. |
| **`Taxable Amount`**| Numeric ($\ge 0$) | Base pre-tax value for that item row. |
| **`CGST Amount`** | Numeric ($\ge 0$) | Central GST amount for Intra-State sales. |
| **`SGST Amount`** | Numeric ($\ge 0$) | State GST amount for Intra-State sales. |
| **`IGST Amount`** | Numeric ($\ge 0$) | Integrated GST amount for Inter-State sales. |
| **`Total Amount`** | Numeric ($\ge 0$) | Gross line total including taxes. |

---

### B. Golden GST Rules for Multi-Item Invoices

1. **Intra-State Invoices (Buyer State == Company State):**
   - Provide non-zero values in `CGST Amount` and `SGST Amount`.
   - Keep `IGST Amount` as `0.0` (or empty) across **all rows** of that invoice.
2. **Inter-State Invoices (Buyer State != Company State):**
   - Provide the combined tax value in `IGST Amount`.
   - Keep `CGST Amount` and `SGST Amount` as `0.0` across **all rows** of that invoice.
3. ⚠️ **Strict Rule: Never mix CGST/SGST and IGST within the same `Invoice No`.** An invoice in GST law must be either 100% Intra-State or 100% Inter-State.

---

## 2. Step-by-Step Application Workflow

```
[ Step 1: Upload Excel ] ──> [ Step 2: Map Headers ] ──> [ Step 3: Tally Sync ]
                                                                 │
[ Step 5: Export XML/Excel ] <── [ Step 4: Master Verification Hub ] ◄──┘
```

---

### Step 1: Source Excel Workbook
* **Action:** Drag and drop your `.xlsx` or `.xls` file.
* **Sheet Selection:** Choose the target worksheet containing the sales register data.
* **Header Row Index:** Specify which row contains column headers (defaults to row `1`).

---

### Step 2: Map Column Headers
* **Action:** Confirm the auto-mapped columns or manually assign dropdown selections.
* **Required Fields:** All 14 standard columns marked `<REQUIRED>` must be mapped.
* **Date Filter Slicer (Optional):** Define a `From Date` and `To Date` to export only a subset of invoices.

---

### Step 3: Tally Prime Integration & Sync
* **Requirement:** Ensure Tally Prime is open with your target company on the default XML port (`9000`).
* **Sync Ledgers:** Downloads all existing Sundry Debtors, States, GSTINs, and Registration Types.
* **Sync Stock Items:** Downloads all existing Stock Items and Units of Measure.

---

### Step 4: Master Verification Hub (Audit & Reconcile)

This hub validates your Excel records against live Tally databases to guarantee error-free imports:

1. **Party Ledgers Audit:**
   - Shows 100% exact matches and fuzzy-matched accounts.
   - Lists non-existing customer ledgers.
   - Click **"Create Missing Ledgers in Tally"** to push all missing customer accounts into Tally with their State and GST registration details in one click.
2. **Stock Items Audit:**
   - Compares Excel product names with Tally inventory.
   - Click **"Create Stock Items in Tally"** to automatically create missing items under your selected Stock Group (e.g. `Primary`).
3. **Units of Measure (UOM) Audit:**
   - Displays all detected units (e.g. `Nos`, `Pcs`, `Kgs`).
   - *Ensure these units exist in Tally under Masters $\rightarrow$ Units of Measure.*

---

### Step 5: Tax Types & Export Hub
* **Tally Company Name:** Enter or verify the exact company name for the XML header.
* **Misc / Round-off Ledger:** Choose your rounding account (e.g. `Misc`, `Round Off`) to automatically balance fractional paise differences between debits and credits.
* **Product Sales Ledgers Mapping:** Map each detected GST rate (e.g. `18%`, `12%`, `0% / Nil Rated`) to its specific Tally Sales Account (e.g. `Goods Sales - 18%`).
* **Tax Types & Rates Mapping:** Map detected output tax categories (e.g. `CGST Output 9%`, `SGST Output 9%`, `IGST Output 18%`) to your exact Tally tax ledger names.
* **Export Buttons:**
  - **`Generate Sales Register XML`:** Creates the final transaction XML file.
  - **`Generate Processed Excel`:** Creates a 2-sheet formatted workbook with item breakdowns and hierarchical invoice groupings.

---

## 3. Impact of Missing, Empty, or Misconfigured Values

| Scenario / Missing Value | System Behavior | Impact on Tally Prime | Resolution |
| :--- | :--- | :--- | :--- |
| **Missing `Invoice No`** | Row cannot be grouped into an invoice; XML generation throws an error. | Import blocked. | Ensure every row has an `Invoice No`. |
| **Blank `Party Name`** | Defaults party name to `"Cash"`. | Posts voucher under `"Cash"` account. | Provide customer name in Excel. |
| **City name used instead of State** *(e.g. `Hyderabad` instead of `Telangana`)* | App writes city name to `<STATENAME>`. | Tally flags GSTR-1 error: *"GST Registration Details invalid or not specified"*. | **Always use official State names** (e.g. `Telangana`). |
| **Mixed CGST/SGST and IGST in same invoice** | Generates both CGST/SGST and IGST ledger credits on the same voucher. | Tally flags GSTR-1 error: *"Incorrect Tax Ledger is selected"*. | Convert all rows of that invoice to 100% IGST or 100% CGST/SGST. |
| **Tally Master State != Invoice Tax Type** *(e.g. Party in Telangana but invoice has CGST/SGST)* | Generates intra-state tax ledgers for an inter-state party. | Tally flags GSTR-1 error: *"Applicable Tax Ledger is not selected"*. | Align the invoice tax columns with the party's registered state in Tally. |
| **UOM does not exist in Tally** | XML imports item with unmapped unit. | Tally displays import error or blocks transaction import. | Create the unit under *Tally Masters $\rightarrow$ Units*. |
| **Product name does not exist in Tally** | Imports inventory item name directly. | If item master is missing, Tally creates an unclassified item or rejects entry. | Use **Step 4: Create Stock Items in Tally** before importing transactions. |
| **Missing / Zero `Taxable Amount`** | Line item rate calculation becomes `0.0`. | Voucher posts as ₹0 base item (Nil Rated). | Ensure taxable amount is populated. |
| **Blank `GST no`** | App marks registration type as `Unregistered/Consumer`. | Recorded as B2C sale in GSTR-1. | Normal behavior for unregistered retail customers. |
| **Unmapped Tax / Sales Ledger in Step 5** | Falls back to default fallback naming (e.g. `Goods Sales - 18%`). | Fails if that exact fallback ledger name is not in Tally. | Select mapped ledgers from dropdowns in Step 5. |

---

## 4. Tally Prime XML Import Instructions

1. Open **Tally Prime** and load your target client company.
2. Press **Alt + O** (or click **Import** in the top navigation bar).
3. Select **Transactions**.
4. Choose **File Path** and select the downloaded XML file (`*_vouchers.xml`).
5. Press **Enter** to start the import.
6. Verify the imported vouchers under **Display More Reports $\rightarrow$ Statutory Reports $\rightarrow$ GST Reports $\rightarrow$ GSTR-1**. All imported vouchers should appear clean with zero *Uncertain Transactions*.

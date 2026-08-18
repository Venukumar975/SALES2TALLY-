# Tally Prime Master Creation & XML Tag Mapping Reference Guide

This document provides a technical specification of the XML schemas, tags, and data transformations used by **SALES2TALLY** to automatically create **Party Ledgers** and **Stock Items** in **Tally Prime** (compatible with Tally Prime 1.x, 2.x, 3.x, 4.x, and 5.x).

---

## 1. Party Name (Customer Ledger) Creation

When creating customer party ledgers in Tally Prime, the XML payload must populate both legacy top-level elements and modern nested sub-lists (`<LEDMAILINGDETAILS.LIST>` and `<LEDGSTREGDETAILS.LIST>`) so that Mailing details and Tax Registration details display correctly in Tally Prime's **Ledger Alteration** screen without showing `* Not Applicable`.

### Field & Tag Mapping Table

| Excel / App Field | Tally Prime XML Tag | Sub-List / Location | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| **Party Name** | `<NAME>` | Root `<LEDGER>` | Unique ledger name in Tally (sanitized & normalized). |
| **Party Name** | `<MAILINGNAME>` | `<LEDMAILINGDETAILS.LIST>` | Name printed on invoices/statements. |
| **Parent Group** | `<PARENT>` | Root `<LEDGER>` | Hardcoded to `Sundry Debtors` (Current Assets). |
| **Bill-by-Bill** | `<ISBILLWISEON>` | Root `<LEDGER>` | Set to `Yes` for tracking outstanding bills and invoice references. |
| **Affects Stock** | `<AFFECTSSTOCK>` | Root `<LEDGER>` | Set to `No` (accounting debtor ledger). |
| **Country** | `<COUNTRYNAME>` | Root `<LEDGER>` | Set to `India`. |
| **Country** | `<COUNTRYOFRESIDENCE>` | Root `<LEDGER>` | Set to `India`. |
| **Country** | `<COUNTRY>` | `<LEDMAILINGDETAILS.LIST>` | Set to `India` under Mailing Details. |
| **State Name** | `<LEDSTATENAME>` | Root `<LEDGER>` | Standardized Tally state name (e.g. `Andhra Pradesh`, `Telangana`). |
| **State Name** | `<STATE>` | `<LEDMAILINGDETAILS.LIST>` | Populates the **State** field in Mailing Details. |
| **State Name** | `<PLACEOFSUPPLY>` | `<LEDGSTREGDETAILS.LIST>` | Populates default **Place of Supply** for GST billing. |
| **GSTIN / UIN** | `<PARTYGSTIN>` | Root `<LEDGER>` | Full 15-character GST identification number. |
| **GSTIN / UIN** | `<GSTIN>` | `<LEDGSTREGDETAILS.LIST>` | Populates the **GSTIN/UIN** field under Tax Registration Details. |
| **Registration Type** | `<GSTREGISTRATIONTYPE>` | Root `<LEDGER>` & `<LEDGSTREGDETAILS.LIST>` | Set to `Regular` if GSTIN is present, otherwise `Unregistered`. |
| **Applicable From** | `<APPLICABLEFROM>` | Both Lists | Set to `20240401` (`01-Apr-2024`) for statutory compliance. |

> [!NOTE]
> **State Inference Logic**: If the Excel sheet has state abbreviations (e.g., `AP`, `TG`, `KA`), code prefixes (`37-AP`, `37-Andhra Pradesh`), or an empty state cell, the application resolves the official state name using the first 2 digits of the party's **GSTIN** via `clean_and_resolve_state()`.

---

### Example Generated XML: Party Ledger

```xml
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>All Masters</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>Sales Ac</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      <!-- Case 1: Regular Customer with GSTIN -->
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <LEDGER NAME="Big Maart Super Market" ACTION="Create">
          <NAME>Big Maart Super Market</NAME>
          <PARENT>Sundry Debtors</PARENT>
          <ISBILLWISEON>Yes</ISBILLWISEON>
          <AFFECTSSTOCK>No</AFFECTSSTOCK>
          <COUNTRYNAME>India</COUNTRYNAME>
          <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
          <LEDSTATENAME>Andhra Pradesh</LEDSTATENAME>
          <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
          <PARTYGSTIN>37ABCDE1234F1Z5</PARTYGSTIN>
          <LEDMAILINGDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <PINCODE></PINCODE>
            <MAILINGNAME>Big Maart Super Market</MAILINGNAME>
            <STATE>Andhra Pradesh</STATE>
            <COUNTRY>India</COUNTRY>
          </LEDMAILINGDETAILS.LIST>
          <LEDGSTREGDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
            <PLACEOFSUPPLY>Andhra Pradesh</PLACEOFSUPPLY>
            <GSTIN>37ABCDE1234F1Z5</GSTIN>
          </LEDGSTREGDETAILS.LIST>
        </LEDGER>
      </TALLYMESSAGE>

      <!-- Case 2: Unregistered Consumer / Cash Party -->
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <LEDGER NAME="Abhilash provision" ACTION="Create">
          <NAME>Abhilash provision</NAME>
          <PARENT>Sundry Debtors</PARENT>
          <ISBILLWISEON>Yes</ISBILLWISEON>
          <AFFECTSSTOCK>No</AFFECTSSTOCK>
          <COUNTRYNAME>India</COUNTRYNAME>
          <COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>
          <LEDSTATENAME>Andhra Pradesh</LEDSTATENAME>
          <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
          <LEDMAILINGDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <PINCODE></PINCODE>
            <MAILINGNAME>Abhilash provision</MAILINGNAME>
            <STATE>Andhra Pradesh</STATE>
            <COUNTRY>India</COUNTRY>
          </LEDMAILINGDETAILS.LIST>
          <LEDGSTREGDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <GSTREGISTRATIONTYPE>Unregistered</GSTREGISTRATIONTYPE>
            <PLACEOFSUPPLY>Andhra Pradesh</PLACEOFSUPPLY>
          </LEDGSTREGDETAILS.LIST>
        </LEDGER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
```

---

## 2. Product Name (Stock Item) Creation

When creating inventory stock items, the application auto-calculates GST tax rates and sets up HSN details with full descriptions.

### Field & Tag Mapping Table

| Excel / App Field | Tally Prime XML Tag | Sub-List / Location | Description & Business Rules |
| :--- | :--- | :--- | :--- |
| **Product** | `<NAME>` | Root `<STOCKITEM>` | Stock item name (e.g. `AMBIP GELFR LEMON 75GX24 Dec 23 IN`). |
| **Parent Group** | `<PARENT>` | Root `<STOCKITEM>` | Set to `Primary` or any stock group selected in the UI modal. |
| **Item Description** | `<DESCRIPTION>` | Root `<STOCKITEM>` | Formatted as **`<Product Name> - <HSN Code>`** for invoice printing. |
| **Unit of Measure** | `<BASEUNITS>` | Root `<STOCKITEM>` | Inferred per-item from mapped Excel **UOM** column (e.g., `Nos`, `Kgs`, `Bags`, `Box`). Falls back to modal default. |
| **GST Applicability** | `<GSTAPPLICABLE>` | Root `<STOCKITEM>` | Set to `Applicable`. |
| **Type of Supply** | `<GSTTYPEOFSUPPLY>` | Root `<STOCKITEM>` | `Goods` or `Services`. |
| **HSN / SAC Code** | `<HSNCODE>` | `<HSNDETAILS.LIST>` | Numeric HSN code extracted from Excel (e.g., `33074900`, `8471`). |
| **HSN Description** | `<HSN>` | `<HSNDETAILS.LIST>` | **CRITICAL:** In Tally Prime XML, the `<HSN>` tag represents the **HSN Description**, populated with **`<Product Name> - <HSN Code>`**. |
| **HSN Source** | `<SRCOFHSNDETAILS>` | `<HSNDETAILS.LIST>` | Set to `Specify Details Here` so Tally uses item-level HSN settings. |
| **Taxability** | `<TAXABILITY>` | `<GSTDETAILS.LIST>` | `Taxable` if taxes > 0, otherwise `Nil Rated`. |
| **GST Source** | `<SRCOFGSTDETAILS>` | `<GSTDETAILS.LIST>` | Set to `Specify Details Here` for item-level GST rate configuration. |
| **State Scope** | `<STATENAME>` | `<STATEWISEDETAILS.LIST>` | `&#4; Any` (applies across inter-state and intra-state transactions). |
| **GST Rate Head** | `<GSTRATEDUTYHEAD>` | `<RATEDETAILS.LIST>` | `IGST` (integrated tax head). |
| **Valuation Type** | `<GSTRATEVALUATIONTYPE>` | `<RATEDETAILS.LIST>` | `Based on Value`. |
| **Calculated GST %** | `<GSTRATE>` | `<RATEDETAILS.LIST>` | Auto-calculated from invoice values: $$\frac{\text{CGST} + \text{SGST}}{\text{Taxable}} \times 100 \quad \text{or} \quad \frac{\text{IGST}}{\text{Taxable}} \times 100$$ |

---

### Example Generated XML: Stock Item

```xml
<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Import</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>All Masters</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVCURRENTCOMPANY>Sales Ac</SVCURRENTCOMPANY>
      </STATICVARIABLES>
    </DESC>
    <DATA>
      <TALLYMESSAGE xmlns:UDF="TallyUDF">
        <STOCKITEM NAME="Mechanical Gaming Keyboard RGB" ACTION="Create">
          <NAME>Mechanical Gaming Keyboard RGB</NAME>
          <DESCRIPTION>Mechanical Gaming Keyboard RGB - 8471</DESCRIPTION>
          <BASEUNITS>Nos</BASEUNITS>
          <GSTAPPLICABLE>Applicable</GSTAPPLICABLE>
          <GSTTYPEOFSUPPLY>Goods</GSTTYPEOFSUPPLY>
          
          <!-- HSN/SAC Details -->
          <HSNDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <HSNCODE>8471</HSNCODE>
            <HSN>Mechanical Gaming Keyboard RGB - 8471</HSN>
            <SRCOFHSNDETAILS>Specify Details Here</SRCOFHSNDETAILS>
          </HSNDETAILS.LIST>

          <!-- GST Rate Details -->
          <GSTDETAILS.LIST>
            <APPLICABLEFROM>20240401</APPLICABLEFROM>
            <TAXABILITY>Taxable</TAXABILITY>
            <SRCOFGSTDETAILS>Specify Details Here</SRCOFGSTDETAILS>
            <STATEWISEDETAILS.LIST>
              <STATENAME>&#4; Any</STATENAME>
              <RATEDETAILS.LIST>
                <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>
                <GSTRATEVALUATIONTYPE>Based on Value</GSTRATEVALUATIONTYPE>
                <GSTRATE>18.0</GSTRATE>
              </RATEDETAILS.LIST>
            </STATEWISEDETAILS.LIST>
          </GSTDETAILS.LIST>
        </STOCKITEM>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
```

---

## 3. Key Technical Notes & Tally Prime Quirks

1. **`<HSN>` vs `<HSNCODE>`**:
   In Tally Prime TDL schema, `<HSNCODE>` holds the numeric tariff classification code, while `<HSN>` holds the text description of the HSN code. Passing the code into `<HSN>` will cause the HSN number to duplicate into the description field.
2. **`ACTION="Create"` Idempotency**:
   Sending `<LEDGER ACTION="Create">` or `<STOCKITEM ACTION="Create">` for an existing master in Tally Prime automatically acts as an update (`Altered: 1`), safely updating missing fields without throwing duplicate master errors.
3. **Escaping Characters**:
   All string values undergo XML entity escaping (`&` $\rightarrow$ `&amp;`, `<` $\rightarrow$ `&lt;`, `>` $\rightarrow$ `&gt;`, `"` $\rightarrow$ `&quot;`, `'` $\rightarrow$ `&apos;`).
4. **Control Characters in Tally XML**:
   Tally sometimes emits unescaped control characters such as `&#4;` (represented as `\x04`). Incoming XML from Tally is cleaned via `clean_tally_xml()` before parsing with `xml.etree.ElementTree`.

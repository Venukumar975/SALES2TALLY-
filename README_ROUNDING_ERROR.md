# Understanding the Tally XML Round-off Mismatch Problem

This document explains a subtle logical discrepancy in how `app.py` computes tax totals and round-off values when compiling XML vouchers, resulting in minor (e.g., 2 paise) credit/debit mismatches.

---

## 1. The Core Issue: "Sum of Rounded" vs "Rounded Sum"

In a Tally XML voucher, the double-entry transaction must balance to exactly `0.00`:
$$\text{Party Debit} - (\text{Taxable Sales} + \text{Tax Ledgers} + \text{Misc Roundoff}) = 0.00$$

However, a discrepancy arises because the **overall tax sum** (used to calculate the roundoff offset) is rounded differently than the **grouped tax ledger lines** written into the final XML.

---

## 2. Walkthrough: Invoice `VMSPE-25-I002900` (`Kalesha Prov`)

Here are the exact numbers calculated for the invoice from the source spreadsheet:

### A. Raw Row Calculations
* **Item 1**: Taxable = `49.05`, CGST (0%) = `0.00`
* **Item 2**: Taxable = `32.99`, CGST (0%) = `0.00`
* **Item 3**: Taxable = `31.46`, CGST (6%) = `1.8876`
* **Item 4**: Taxable = `83.54`, CGST (9%) = `7.5186`
* **Item 5**: Taxable = `83.54`, CGST (9%) = `7.5186`
* **Item 6**: Taxable = `128.11`, CGST (9%) = `11.5299`

* **Total Taxable Sum**: `408.69`
* **Raw Sum of all CGST rows**: $1.8876 + 7.5186 + 7.5186 + 11.5299 = 28.4547$

---

### B. Path 1: How the Roundoff Offset is calculated in `app.py`
The code rounds the **overall sum of CGST** to 2 decimals first:
$$\text{Total CGST Amount} = \text{round}(28.4547, 2) = \mathbf{28.45}$$
$$\text{Total SGST Amount} = \text{round}(28.4547, 2) = \mathbf;{28.45}$$

Using these totals, the code calculates the total value before round-off:
$$\text{Credits Sum} = 408.69 \text{ (Taxable)} + 28.45 \text{ (CGST)} + 28.45 \text{ (SGST)} = \mathbf{465.59}$$

The party debit total is rounded to the nearest integer:
$$\text{Rounded Party Debit} = \text{round}(465.60 \text{ invoice amount}) = \mathbf{466.00}$$

Finally, the roundoff offset (`Misc`) is computed as:
$$\text{Misc Roundoff} = 466.00 \text{ (Debit)} - 465.59 \text{ (Credits)} = \mathbf{0.41}$$

---

### C. Path 2: How Tax Ledgers are written in the XML
In the XML, the CGST is grouped by tax rate and rounded per rate category:
* **CGST Output 6%**: `1.8876` $\rightarrow$ rounds to **`1.89`**
* **CGST Output 9%**: $7.5186 + 7.5186 + 11.5299 = 26.5671$ $\rightarrow$ rounds to **`26.57`**

The sum of CGST entries actually posted to the XML is:
$$\text{Actual CGST in XML} = 1.89 + 26.57 = \mathbf{28.46}$$
$$\text{Actual SGST in XML} = 1.89 + 26.57 = \mathbf{28.46}$$

---

### D. The Discrepancy
When Tally/Review Desk sums all the posted XML nodes:
* Taxable Items: `408.69`
* CGST: `1.89` + `26.57` = `28.46`
* SGST: `1.89` + `26.57` = `28.46`
* Misc (Roundoff): `0.41`
$$\text{Total Credits written to XML} = 408.69 + 28.46 + 28.46 + 0.41 = \mathbf{466.02}$$
* **Party Debit**: **`466.00`**

This creates a **`0.02` (2 paise) mismatch**, causing the voucher to be flagged as imbalanced.

---

## 3. The Corrective Logic

To prevent this discrepancy in future XML generation scripts, the roundoff offset should be calculated **after grouping and rounding the tax lines**, rather than from the raw sum.

### Proposed Algorithm:
1. **Group and round tax lines** to determine the exact amounts that will be written into the XML:
   * `cgst_xml_total = sum(round(amt, 2) for amt in cgst_groups.values())`
   * `sgst_xml_total = sum(round(amt, 2) for amt in sgst_groups.values())`
2. **Calculate credits sum** using these XML-ready totals:
   * `exact_credits_sum = total_taxable_amount + cgst_xml_total + sgst_xml_total`
3. **Calculate roundoff offset** from the balanced total:
   * `roundoff_offset = round(rounded_total - exact_credits_sum, 2)`

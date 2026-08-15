// Global Configuration & State
const targetFields = [
    { id: "Invoice Date", label: "Invoice Date", desc: "Date of the invoice transaction", required: true },
    { id: "Invoice No", label: "Invoice No", desc: "Invoice or reference identifier", required: true },
    { id: "Party Name", label: "Party Name", desc: "Customer or Supplier business ledger name", required: true },
    { id: "GST no", label: "GST no", desc: "Supplier/Buyer GSTIN (Optional, blank if empty)", required: false },
    { id: "State Name", label: "State Name", desc: "Place of Supply / State name", required: true },
    { id: "Product", label: "Product", desc: "Name of the item or description of service", required: true },
    { id: "HSN Code", label: "HSN Code", desc: "HSN/SAC code of the product", required: true },
    { id: "Qty", label: "Qty", desc: "Item quantity", required: true },
    { id: "Taxable Amount", label: "Taxable Amount", desc: "Pre-tax taxable value", required: true },
    { id: "CGST Amount", label: "CGST Amount", desc: "Central GST amount", required: true },
    { id: "SGST Amount", label: "SGST Amount", desc: "State GST amount", required: true },
    { id: "IGST Amount", label: "IGST Amount", desc: "Integrated GST amount", required: true },
    { id: "Total Amount", label: "Total Amount", desc: "Net invoice amount", required: true },
    { id: "UOM", label: "UOM", desc: "Unit of Measurement (e.g. Nos, Pcs)", required: true }
];

// Fuzzy auto-match keyword dictionary
const autoMatches = {
    "Invoice Date": ["invoice date", "inv date", "date", "invdate", "invoicedate", "vch date", "voucher date"],
    "Invoice No": ["invoice no", "inv no", "invoice number", "inv number", "invoice_no", "inv_no", "voucher no", "vch no", "inv_number", "bill no"],
    "Party Name": ["party name", "party", "supplier name", "ledger name", "customer name", "particulars", "party_name"],
    "GST no": ["gst no", "gst", "gstin", "gstin of supplier", "supplier gstin", "party gstin", "gst_no", "gstin/uin", "gstin uin"],
    "State Name": ["state name", "state", "place of supply", "pos", "state_name", "place_of_supply"],
    "Product": ["product", "item name", "item", "description", "product description", "stock item", "particular", "item_name"],
    "HSN Code": ["hsn code", "hsn", "hsn/sac", "hsn_code", "hsn_sac"],
    "Qty": ["qty", "quantity", "billed qty", "actual qty", "billed_qty"],
    "Taxable Amount": ["taxable amount", "taxable value", "taxable val", "taxable", "taxable amt", "taxable_amount", "taxable_value", "taxable_val", "taxable amt (₹)"],
    "CGST Amount": ["cgst amount", "cgst amt", "central tax", "cgst", "cgst_amount", "cgst amt (₹)", "central tax (₹)"],
    "SGST Amount": ["sgst amount", "sgst amt", "state tax", "utgst", "sgst", "sgst_amount", "sgst amt (₹)", "state tax (₹)", "state/ut tax"],
    "IGST Amount": ["igst amount", "igst amt", "integrated tax", "igst", "igst_amount", "igst amt (₹)", "integrated tax (₹)"],
    "Total Amount": ["total amount", "total amt", "invoice value", "inv value", "total", "total_amount", "net amount", "total amt (₹)", "invoice value (₹)"],
    "UOM": ["uom", "unit", "units", "uom name", "nos", "pcs", "unit of measure"]
};

// Global App State
let tempFileId = "";
let originalFilename = "";
let excelHeaders = [];
let tallyLedgerList = [];
let detectedTaxKeys = [];
let lastNonExistingParties = [];
let lastNonExistingProducts = [];

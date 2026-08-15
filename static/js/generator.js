// Sales Register XML & Processed Excel Generators

async function generateSalesXML() {
    if (lastNonExistingParties && lastNonExistingParties.length > 0) {
        showStatus("mapping-status", null, "⚠️ Cannot generate XML: You have non-existing party names. Please create them in Tally first.", "error");
        return;
    }
    if (lastNonExistingProducts && lastNonExistingProducts.length > 0) {
        showStatus("mapping-status", null, "⚠️ Cannot generate XML: You have missing products. Please add them to your Tally inventory first.", "error");
        return;
    }

    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    const mappings = {};
    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        }
    });

    const ledgerCo = document.getElementById("tally_ledger_company_select").value;
    const xmlCompanyName = document.getElementById("xml_company_name").value.trim();
    const salesLedger = document.getElementById("sales_ledger_select").value;
    const miscLedger = document.getElementById("misc_ledger_select").value;

    if (!salesLedger) {
        showStatus("mapping-status", null, "⚠️ Please select a Sales Ledger Account first.", "error");
        return;
    }
    if (!xmlCompanyName) {
        showStatus("mapping-status", null, "⚠️ Please enter the Tally Company Name for XML Import.", "error");
        return;
    }

    const btn = document.getElementById("btn-generate-xml");
    btn.disabled = true;
    document.getElementById("success-container").style.display = "none";
    document.getElementById("excel-success-container").style.display = "none";
    showStatus("mapping-status", "generate-xml-loader", "Generating Sales Register XML Vouchers...", "info");

    const fromDate = document.getElementById("filter-from-date").value;
    const toDate = document.getElementById("filter-to-date").value;

    const taxLedgerMappings = {};
    document.querySelectorAll(".tax-rate-mapping-dropdown").forEach(dropdown => {
        const key = dropdown.getAttribute("data-tax-key");
        if (dropdown.value) {
            taxLedgerMappings[key] = dropdown.value;
        }
    });

    try {
        const res = await fetch("/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                original_filename: originalFilename,
                ledger_company: ledgerCo,
                xml_company_name: xmlCompanyName,
                sales_ledger_name: salesLedger,
                misc_ledger_name: miscLedger,
                from_date: fromDate,
                to_date: toDate,
                header_row: rowVal,
                tax_ledger_mappings: taxLedgerMappings
            })
        });
        const data = await res.json();

        if (data.success) {
            const downloadBtn = document.getElementById("download-link");
            downloadBtn.href = `/download/${data.filename}`;
            
            hideStatus("mapping-status");
            document.getElementById("success-container").style.display = "flex";
        } else {
            showStatus("mapping-status", null, `❌ Generation failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        btn.disabled = false;
    }
}

async function generateProcessedExcel() {
    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    const mappings = {};
    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        }
    });

    if (!tempFileId || !sheet) {
        showStatus("mapping-status", null, "⚠️ Please upload a file and select a sheet first.", "error");
        return;
    }

    document.getElementById("success-container").style.display = "none";
    document.getElementById("excel-success-container").style.display = "none";

    const btn = document.getElementById("btn-generate-excel");
    btn.disabled = true;
    showStatus("mapping-status", "generate-excel-loader", "Generating Processed Excel...", "info");

    const fromDate = document.getElementById("filter-from-date").value;
    const toDate = document.getElementById("filter-to-date").value;

    try {
        const res = await fetch("/generate_excel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                original_filename: originalFilename,
                from_date: fromDate,
                to_date: toDate,
                header_row: rowVal
            })
        });
        const data = await res.json();

        if (data.success) {
            const downloadBtn = document.getElementById("excel-download-link");
            downloadBtn.href = `/download/${data.filename}`;
            
            hideStatus("mapping-status");
            document.getElementById("excel-success-container").style.display = "flex";
        } else {
            showStatus("mapping-status", null, `❌ Excel generation failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        btn.disabled = false;
    }
}

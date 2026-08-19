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
    const miscLedger = document.getElementById("misc_ledger_select").value;

    if (!xmlCompanyName) {
        showStatus("mapping-status", null, "⚠️ Please enter the Tally Company Name for XML Import.", "error");
        return;
    }

    const salesLedgerMappings = {};
    document.querySelectorAll(".sales-rate-mapping-dropdown").forEach(dropdown => {
        const rate = dropdown.getAttribute("data-sales-rate");
        if (dropdown.value) {
            salesLedgerMappings[rate] = dropdown.value;
        }
    });

    const taxLedgerMappings = {};
    document.querySelectorAll(".tax-rate-mapping-dropdown").forEach(dropdown => {
        const key = dropdown.getAttribute("data-tax-key");
        if (dropdown.value) {
            taxLedgerMappings[key] = dropdown.value;
        }
    });

    const btn = document.getElementById("btn-generate-xml");
    btn.disabled = true;
    document.getElementById("success-container").style.display = "none";
    document.getElementById("excel-success-container").style.display = "none";
    showStatus("export-status", "generate-xml-loader", "Generating Sales Register XML Vouchers...", "info");

    const fromDate = document.getElementById("filter-from-date").value;
    const toDate = document.getElementById("filter-to-date").value;

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
                sales_ledger_mappings: salesLedgerMappings,
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
            downloadBtn.onclick = (e) => {
                e.preventDefault();
                triggerFileDownload(data.filename);
            };
            
            hideStatus("export-status");
            document.getElementById("success-container").style.display = "flex";

            // Automatically open XML Pre-Flight Integrity Verification Modal
            if (data.audit_report) {
                renderAndOpenXmlAuditModal(data.filename, data.audit_report);
            }
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
    showStatus("export-status", "generate-excel-loader", "Generating Processed Excel...", "info");

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
            downloadBtn.onclick = (e) => {
                e.preventDefault();
                triggerFileDownload(data.filename);
            };
            
            hideStatus("export-status");
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

async function triggerFileDownload(filename) {
    if (!filename) return;

    // 1. Try PyWebView native Windows Save As file dialog
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file_dialog) {
            const res = await window.pywebview.api.save_file_dialog(filename);
            if (res && res.success) {
                alert(`✅ File successfully saved to:\n\n${res.saved_to}`);
                return;
            } else if (res && res.cancelled) {
                return; // User clicked cancel in file picker
            }
        }
    } catch (e) {
        console.warn("PyWebView Save Dialog fallback triggered:", e);
    }

    // 2. Direct save to user's Downloads directory via backend API
    try {
        const res = await fetch("/api/save-to-downloads", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: filename })
        });
        const data = await res.json();
        if (data.success) {
            alert(`✅ File saved to your Downloads folder:\n\n${data.saved_to}`);
            return;
        }
    } catch (e) {
        console.warn("Downloads folder save fallback:", e);
    }

    // 3. Fallback: JavaScript blob download
    try {
        const response = await fetch(`/download/${filename}`);
        if (!response.ok) throw new Error("Could not fetch file");
        const blob = await response.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            document.body.removeChild(a);
            window.URL.revokeObjectURL(blobUrl);
        }, 2000);
    } catch (err) {
        alert("Download error: " + err.message);
    }
}

// ==============================================================================
// XML PRE-FLIGHT AUDIT MODAL RENDERER
// ==============================================================================
function renderAndOpenXmlAuditModal(filename, audit) {
    if (!audit) return;

    const total = audit.total_vouchers || 0;

    // 1. Top KPI Summary
    const vEl = document.getElementById("audit-kpi-vouchers");
    if (vEl) vEl.innerText = total.toLocaleString();

    const unbal = audit.unbalanced_count || 0;
    const balEl = document.getElementById("audit-kpi-balance");
    const unbalEl = document.getElementById("audit-kpi-unbalanced");
    if (balEl) {
        if (unbal === 0) {
            balEl.innerText = "100% Balanced";
            balEl.className = "kpi-value text-emerald";
            if (unbalEl) unbalEl.innerText = "0 Unbalanced Invoices";
        } else {
            balEl.innerText = `${unbal} Unbalanced`;
            balEl.className = "kpi-value text-danger";
            if (unbalEl) unbalEl.innerText = "Check Ledger Balances";
        }
    }

    const totalDebits = audit.total_debits || 0;
    const amtEl = document.getElementById("audit-kpi-amount");
    if (amtEl) {
        amtEl.innerText = `₹${totalDebits.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    // 2. Table Rows with Simple Non-Technical Accounting Terms
    const tVch = document.getElementById("tab-total-vouchers");
    if (tVch) tVch.innerText = `${total.toLocaleString()} Invoices Successfully Created from Excel`;

    const missingInv = audit.missing_inv_no || 0;
    const tInv = document.getElementById("tab-inv-no-details");
    if (tInv) tInv.innerText = `${total - missingInv} / ${total} Bills matched with exact Invoice Numbers`;

    const missingDates = audit.missing_dates || 0;
    const tDates = document.getElementById("tab-dates-details");
    if (tDates) tDates.innerText = `${total - missingDates} / ${total} Invoices matched with correct dates`;

    const missingState = audit.missing_state || 0;
    const tParty = document.getElementById("tab-party-details");
    if (tParty) tParty.innerText = `${total - missingState} / ${total} Invoices matched with Customer details`;

    const b2b = audit.b2b_count || 0;
    const b2c = audit.b2c_count || 0;
    const tGst = document.getElementById("tab-gst-classification");
    if (tGst) tGst.innerHTML = `B2B Invoices: <strong>${b2b}</strong> (with GSTIN) &nbsp;|&nbsp; B2C Invoices: <strong>${b2c}</strong>`;

    const partiesCount = audit.unique_parties_count || 0;
    const itemsCount = audit.unique_items_count || 0;
    const tMasters = document.getElementById("tab-masters-validity");
    if (tMasters) tMasters.innerText = `All Customer & Product names verified in Tally`;

    const tBal = document.getElementById("tab-balance-details");
    if (tBal) {
        if (unbal === 0) {
            tBal.innerHTML = `100% Matched (Zero Difference Across All Invoices)`;
        } else {
            tBal.innerHTML = `<span class="text-danger">${unbal} invoices have debit/credit difference!</span>`;
        }
    }

    // 3. Download Button
    const dlBtn = document.getElementById("audit-download-xml-btn");
    if (dlBtn) {
        dlBtn.href = `/download/${filename}`;
        dlBtn.onclick = (e) => {
            e.preventDefault();
            triggerFileDownload(filename);
        };
    }

    // 4. Open Modal
    const modal = document.getElementById("xml-audit-modal");
    if (modal) {
        modal.classList.add("active");
        modal.style.display = "flex";
    }
}

function closeXmlAuditModal() {
    const modal = document.getElementById("xml-audit-modal");
    if (modal) {
        modal.style.display = "none";
    }
}



window.closeXmlAuditModal = function() {
    const modal = document.getElementById("xml-audit-modal");
    if (modal) {
        modal.classList.remove("active");
        modal.style.display = "none";
    }
};

document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
        window.closeXmlAuditModal();
    }
});

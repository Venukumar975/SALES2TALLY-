/**
 * SALES2TALLY - Accounting Invoice Workflow (Spares HSN Ledgers)
 * 100% matched to Item Invoice Enterprise Design System.
 */

const AccountingState = {
    fileId: null,
    filename: null,
    sheets: [],
    currentSheet: null,
    headers: [],
    columnMappings: {},
    availableLedgers: [],
    detectedHsn: [],
    detectedTaxes: [],
    generatedXmlFilename: null,
    generatedExcelFilename: null
};

const ACCT_TARGET_FIELDS = [
    {
        id: "invoice_no",
        label: "Invoice Number",
        required: true,
        desc: "Groups multi-line product rows into a single Tally sales invoice"
    },
    {
        id: "invoice_date",
        label: "Invoice Date",
        required: true,
        desc: "Voucher date used for chronological ordering in Day Book"
    },
    {
        id: "hsn_code",
        label: "HSN Code",
        required: true,
        desc: "Product HSN/SAC code used to generate rate-wise Spares Ledgers"
    },
    {
        id: "selling_price",
        label: "Selling Price / Taxable",
        required: true,
        desc: "Base taxable amount credited to Spares HSN Ledger"
    },
    {
        id: "cgst_amount",
        label: "CGST Amount",
        required: true,
        desc: "Central GST tax amount for intra-state spares"
    },
    {
        id: "sgst_amount",
        label: "SGST Amount",
        required: true,
        desc: "State GST tax amount for intra-state spares"
    },
    {
        id: "igst_amount",
        label: "IGST Amount",
        required: false,
        desc: "Integrated GST tax amount for inter-state spares"
    }
];

// 1. MODE SWITCHER
function switchAppMode(mode) {
    const itemSection = document.getElementById("section-item-invoice");
    const acctSection = document.getElementById("section-accounting-invoice");
    const itemBtn = document.getElementById("tab-item-mode");
    const acctBtn = document.getElementById("tab-accounting-mode");

    if (mode === "accounting") {
        if (itemSection) itemSection.style.display = "none";
        if (acctSection) acctSection.style.display = "block";
        if (itemBtn) itemBtn.classList.remove("active");
        if (acctBtn) acctBtn.classList.add("active");
        
        loadAcctSavedCompanies();
    } else {
        if (itemSection) itemSection.style.display = "block";
        if (acctSection) acctSection.style.display = "none";
        if (itemBtn) itemBtn.classList.add("active");
        if (acctBtn) acctBtn.classList.remove("active");
    }
}

function acctScrollTo(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        if (el.style.display === "none") {
            el.style.display = "block";
        }
        const yOffset = -90; // account for sticky header
        const y = el.getBoundingClientRect().top + window.pageYOffset + yOffset;
        window.scrollTo({ top: y, behavior: "smooth" });
    }
}

function updateAcctStepper(activeStep) {
    for (let i = 1; i <= 4; i++) {
        const node = document.getElementById(`acct-step-node-${i}`);
        const line = document.getElementById(`acct-step-line-${i}`);
        if (node) {
            if (i <= activeStep) {
                node.classList.add("active");
            } else {
                node.classList.remove("active");
            }
        }
        if (line) {
            if (i < activeStep) {
                line.style.background = "var(--brand-primary)";
                line.style.boxShadow = "0 0 10px rgba(16, 185, 129, 0.4)";
            } else {
                line.style.background = "var(--border-card)";
                line.style.boxShadow = "none";
            }
        }
    }
}

// 2. LOAD SAVED COMPANIES (ACCOUNTING INVOICE MODE)
async function loadAcctSavedCompanies() {
    try {
        const res = await fetch("/api/accounting/saved-companies");
        const data = await res.json();
        if (data.success) {
            const select = document.getElementById("acct_company_select");
            if (!select) return;

            const curVal = select.value || AccountingState.tallyCompany || "";
            select.innerHTML = '<option value="">-- Select Saved Company --</option>';

            if (data.companies && data.companies.length > 0) {
                data.companies.forEach(co => {
                    const opt = document.createElement("option");
                    opt.value = co.company_name;
                    const syncInfo = co.last_sync ? ` • Sync: ${co.last_sync}` : '';
                    opt.textContent = `${co.display_name} (${co.count} Ledgers${syncInfo})`;
                    select.appendChild(opt);
                });
            }

            const newOpt = document.createElement("option");
            newOpt.value = "__NEW__";
            newOpt.textContent = "+ Enter New Company Name...";
            select.appendChild(newOpt);

            // Populate datalist for modal input if open companies in Tally exist
            const datalist = document.getElementById("acct_open_companies_datalist");
            if (datalist && data.open_companies) {
                datalist.innerHTML = "";
                data.open_companies.forEach(c => {
                    const dOpt = document.createElement("option");
                    dOpt.value = c;
                    datalist.appendChild(dOpt);
                });
            }

            // Keep default "-- Select Saved Company --" on fresh load.
            // NEVER auto-load any company ledgers unless the user manually selects from the dropdown.
            if (AccountingState.tallyCompany && Array.from(select.options).some(o => o.value === AccountingState.tallyCompany)) {
                select.value = AccountingState.tallyCompany;
            } else {
                select.value = "";
            }
        }
    } catch (e) {
        console.warn("Could not load saved accounting companies:", e);
    }
}

async function onAcctCompanySelectChanged() {
    const select = document.getElementById("acct_company_select");
    if (!select) return;
    const val = select.value;
    if (val === "__NEW__") {
        select.value = AccountingState.tallyCompany || "";
        openAcctSyncModal();
        return;
    }
    if (!val) {
        AccountingState.tallyCompany = null;
        AccountingState.availableLedgers = [];
        const statusBox = document.getElementById("acct-tally-sync-status");
        if (statusBox) statusBox.style.display = "none";
        await onAcctSheetChanged();
        return;
    }
    await loadAcctCompanyLedgers(val);
}

async function loadAcctCompanyLedgers(companyName) {
    if (!companyName) return;
    AccountingState.tallyCompany = companyName;

    const statusBox = document.getElementById("acct-tally-sync-status");
    try {
        const res = await fetch("/api/accounting/load-company", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name: companyName })
        });
        const data = await res.json();
        if (data.success) {
            AccountingState.availableLedgers = data.ledgers || [];
            if (statusBox) {
                const syncInfo = data.last_sync ? ` | Last sync date: ${data.last_sync}` : '';
                statusBox.textContent = `✓ Loaded ${data.count} ledgers (${data.company_name})${syncInfo}`;
                statusBox.className = "status-box status-success";
                statusBox.style.display = "block";
            }
            if (AccountingState.fileId) {
                await onAcctSheetChanged();
            } else {
                populateAcctDropdowns(null, null);
            }
        } else {
            if (statusBox) {
                statusBox.textContent = `⚠️ Could not load cache for ${companyName}: ${data.error}`;
                statusBox.className = "status-box status-error";
                statusBox.style.display = "block";
            }
        }
    } catch (e) {
        console.error("Failed to load company ledgers:", e);
    }
}

function openAcctSyncModal() {
    const modal = document.getElementById("acct-sync-ledgers-modal");
    const input = document.getElementById("acct_sync_modal_company_name");
    if (!modal) return;
    const curCo = document.getElementById("acct_company_select")?.value || AccountingState.tallyCompany || "";
    if (input) {
        input.value = (curCo && curCo !== "__NEW__") ? curCo : "";
        setTimeout(() => input.focus(), 100);
    }
    modal.style.display = "flex";
}

function closeAcctSyncModal() {
    const modal = document.getElementById("acct-sync-ledgers-modal");
    if (modal) modal.style.display = "none";
}

async function startAcctModalSync() {
    const input = document.getElementById("acct_sync_modal_company_name");
    const companyName = (input?.value || "").trim();
    if (!companyName) {
        alert("Please enter the Company Name exactly as saved in Gateway of Tally.");
        return;
    }

    const btn = document.getElementById("btn-acct-modal-start-sync");
    const loader = document.getElementById("acct-modal-sync-loader");
    const btnLabel = document.getElementById("acct-modal-sync-btn-label");
    const statusBox = document.getElementById("acct-tally-sync-status");

    if (btn) btn.disabled = true;
    if (loader) loader.style.display = "inline-block";
    if (btnLabel) btnLabel.textContent = "Syncing...";

    try {
        const res = await fetch("/api/accounting/sync-tally", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name: companyName })
        });
        const data = await res.json();
        if (!data.success) {
            alert("Tally Sync Error: " + (data.error || "Unknown"));
            if (statusBox) {
                statusBox.textContent = "❌ " + (data.error || "Tally sync failed");
                statusBox.className = "status-box status-error";
                statusBox.style.display = "block";
            }
            return;
        }

        closeAcctSyncModal();

        AccountingState.tallyCompany = data.company_name;
        AccountingState.availableLedgers = data.ledgers || [];

        if (statusBox) {
            const syncInfo = data.last_sync ? ` | Last sync date: ${data.last_sync}` : '';
            statusBox.textContent = `✓ Loaded ${data.count} ledgers (${data.company_name})${syncInfo}`;
            statusBox.className = "status-box status-success";
            statusBox.style.display = "block";
        }

        await loadAcctSavedCompanies();
        const select = document.getElementById("acct_company_select");
        if (select) select.value = data.company_name;

        if (AccountingState.fileId) {
            await onAcctSheetChanged();
        } else {
            populateAcctDropdowns(null, null);
        }

    } catch (e) {
        alert("Sync request failed: " + e.message);
    } finally {
        if (btn) btn.disabled = false;
        if (loader) loader.style.display = "none";
        if (btnLabel) btnLabel.textContent = "Start Sync";
    }
}

// 3. FILE UPLOAD & DRAG DROP
document.addEventListener("DOMContentLoaded", () => {
    const dropzone = document.getElementById("acct-dropzone");
    const fileInput = document.getElementById("acct_excel_file");

    if (!dropzone || !fileInput) return;

    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("dragover");
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("dragover");
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            handleAcctFileUpload(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleAcctFileUpload(e.target.files[0]);
        }
    });

    // Do not load any companies on DOMContentLoaded; only load dropdown when user switches to Accounting mode
});

function resetAcctFile() {
    AccountingState.fileId = null;
    AccountingState.filename = null;
    AccountingState.sheets = [];
    AccountingState.headers = [];
    AccountingState.columnMappings = {};

    document.getElementById("acct_excel_file").value = "";
    document.getElementById("acct-file-info-container").style.display = "none";
    document.getElementById("acct-sheet-select-container").style.display = "none";
    const slicer = document.getElementById("acct-date-slicer-container");
    if (slicer) slicer.style.display = "none";
    document.getElementById("acct-card-mapping").style.display = "none";
    document.getElementById("acct-card-tally").style.display = "none";
    document.getElementById("acct-card-export").style.display = "none";
}

async function handleAcctFileUpload(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append("excel_file", file);

    const fileInfo = document.getElementById("acct-file-info-container");
    const fileNameDisplay = document.getElementById("acct-uploaded-filename");
    const sheetSelectContainer = document.getElementById("acct-sheet-select-container");
    const sheetSelect = document.getElementById("acct-sheet-select");

    try {
        const res = await fetch("/api/accounting/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();
        if (!data.success) {
            alert("Upload failed: " + (data.error || "Unknown error"));
            return;
        }

        AccountingState.fileId = data.file_id;
        AccountingState.filename = data.original_filename;
        AccountingState.sheets = data.sheets || [];

        if (fileNameDisplay) fileNameDisplay.textContent = data.original_filename;
        if (sheetSelect) {
            sheetSelect.innerHTML = "";
            AccountingState.sheets.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s;
                opt.textContent = s;
                sheetSelect.appendChild(opt);
            });
        }
        if (fileInfo) fileInfo.style.display = "flex";
        if (sheetSelectContainer) sheetSelectContainer.style.display = "flex";

        // Analyze first sheet
        await onAcctSheetChanged();
    } catch (e) {
        alert("Upload error: " + e.message);
    }
}

// 4. SHEET CHANGED & ANALYSIS
async function onAcctSheetChanged() {
    if (!AccountingState.fileId) {
        populateAcctDropdowns(null, null);
        return;
    }

    const sheetSelect = document.getElementById("acct-sheet-select");
    const sheetName = sheetSelect ? sheetSelect.value : (AccountingState.sheets[0] || 0);
    AccountingState.currentSheet = sheetName;

    const companyName = (document.getElementById("acct_company_select")?.value || AccountingState.tallyCompany || "").trim();

    try {
        // Also fetch headers for this sheet so dropdowns have all columns
        const headRes = await fetch("/get-headers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: AccountingState.fileId,
                sheet_name: sheetName,
                header_row: document.getElementById("acct-header-row")?.value || 1
            })
        });
        const headData = await headRes.json();
        AccountingState.headers = headData.headers || [];

        const res = await fetch("/api/accounting/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: AccountingState.fileId,
                sheet_name: sheetName,
                company_name: companyName,
                column_mappings: AccountingState.columnMappings
            })
        });

        const data = await res.json();
        if (!data.success) {
            alert("Analysis failed: " + (data.error || "Unknown error"));
            return;
        }

        AccountingState.columnMappings = data.column_mappings;
        AccountingState.detectedHsn = data.detected_hsn_ledgers || [];
        AccountingState.detectedTaxes = data.detected_tax_ledgers || [];
        AccountingState.availableLedgers = data.available_ledgers || [];

        // Setup Date Filter Slicer (Matched to Item Invoice design)
        updateAcctDateSlicer(data.min_date, data.max_date);

        // Build Card 2: Mapping Grid (Matched to Item Invoice design)
        buildAcctMappingGrid(AccountingState.headers, data.column_mappings);

        // Build Card 3 & 4: HSN Spares & Tax Ledgers
        renderAcctHsnMappingGrid(AccountingState.detectedHsn);
        renderAcctTaxesMappingGrid(AccountingState.detectedTaxes);
        populateAcctDropdowns(data.matched_misc_ledger, data.suggested_party);

        // Reveal remaining workflow cards
        document.getElementById("acct-card-mapping").style.display = "block";
        document.getElementById("acct-card-tally").style.display = "block";
        document.getElementById("acct-card-export").style.display = "block";

    } catch (e) {
        alert("Failed to analyze sheet: " + e.message);
    }
}

// 5. BUILD MAPPING GRID (EXACT SAME HTML / DOM AS ITEM INVOICE)
function buildAcctMappingGrid(headers, currentMappings) {
    const grid = document.getElementById("acct-mapping-grid-container");
    if (!grid) return;
    grid.innerHTML = "";

    ACCT_TARGET_FIELDS.forEach(field => {
        const row = document.createElement("div");
        row.className = "mapping-row";
        row.id = `acct-row-${field.id}`;

        const isMapped = Boolean(currentMappings[field.id]);
        if (isMapped) row.classList.add("mapped");

        // Left Section: Label + Badges + Description
        const labelDiv = document.createElement("div");
        labelDiv.className = "mapping-label";

        const titleSpan = document.createElement("span");
        titleSpan.className = "mapping-title";
        titleSpan.innerText = field.label + " ";

        if (field.required) {
            const reqBadge = document.createElement("span");
            reqBadge.className = "badge badge-required";
            reqBadge.innerText = "REQUIRED";
            titleSpan.appendChild(reqBadge);
        } else {
            const optBadge = document.createElement("span");
            optBadge.className = "badge badge-optional";
            optBadge.innerText = "OPTIONAL";
            titleSpan.appendChild(optBadge);
        }

        const descSpan = document.createElement("span");
        descSpan.className = "mapping-desc";
        descSpan.innerText = field.desc;

        labelDiv.appendChild(titleSpan);
        labelDiv.appendChild(descSpan);

        // Auto-mapped indicator (golden lightning badge)
        const autoIndicator = document.createElement("div");
        autoIndicator.className = "auto-mapped-indicator";
        autoIndicator.id = `acct-auto-ind-${field.id}`;
        autoIndicator.style.display = isMapped ? "block" : "none";
        autoIndicator.innerHTML = `
            <svg width="13" height="13" fill="#f59e0b" stroke="#f59e0b" viewBox="0 0 24 24" style="vertical-align: -2px; margin-right: 4px;">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
            </svg>
            <span style="color: #fbbf24; font-weight: 700;">Auto-matched</span>
        `;
        labelDiv.appendChild(autoIndicator);

        // Right Section: Glowing Emerald Dot + Select Wrapper
        const selectContainer = document.createElement("div");
        selectContainer.className = "mapping-select-container";

        const statusIndicator = document.createElement("div");
        statusIndicator.className = "mapping-status";
        statusIndicator.id = `acct-status-dot-${field.id}`;

        const wrapper = document.createElement("div");
        wrapper.className = "select-wrapper";

        const select = document.createElement("select");
        select.id = `acct-select-${field.id}`;
        select.innerHTML = '<option value="">-- Unmapped --</option>';

        headers.forEach(h => {
            const opt = document.createElement("option");
            opt.value = h;
            opt.innerText = h;
            if (currentMappings[field.id] === h) {
                opt.selected = true;
            }
            select.appendChild(opt);
        });

        select.addEventListener("change", (e) => {
            AccountingState.columnMappings[field.id] = e.target.value;
            if (e.target.value) {
                row.classList.add("mapped");
                autoIndicator.style.display = "block";
            } else {
                row.classList.remove("mapped");
                autoIndicator.style.display = "none";
            }
            // Dynamically update date slicer if invoice date column changed
            if (field.id === "invoice_date") {
                fetchAcctDateRange(e.target.value);
            }
        });

        wrapper.appendChild(select);
        selectContainer.appendChild(statusIndicator);
        selectContainer.appendChild(wrapper);

        row.appendChild(labelDiv);
        row.appendChild(selectContainer);
        grid.appendChild(row);
    });
}

function updateAcctDateSlicer(minDate, maxDate) {
    const container = document.getElementById("acct-date-slicer-container");
    const fromInput = document.getElementById("acct-filter-from-date");
    const toInput = document.getElementById("acct-filter-to-date");
    if (!container || !fromInput || !toInput) return;

    if (minDate && maxDate) {
        fromInput.value = minDate;
        toInput.value = maxDate;
        fromInput.min = minDate;
        fromInput.max = maxDate;
        toInput.min = minDate;
        toInput.max = maxDate;
        container.style.display = "block";
    } else {
        container.style.display = "none";
    }
}

async function fetchAcctDateRange(dateCol) {
    const container = document.getElementById("acct-date-slicer-container");
    if (!AccountingState.fileId || !dateCol) {
        if (container) container.style.display = "none";
        return;
    }
    try {
        const res = await fetch("/api/accounting/get-date-range", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: AccountingState.fileId,
                sheet_name: AccountingState.currentSheet,
                date_col: dateCol
            })
        });
        const data = await res.json();
        if (data.success && data.min_date && data.max_date) {
            updateAcctDateSlicer(data.min_date, data.max_date);
        } else {
            if (container) container.style.display = "none";
        }
    } catch (e) {
        console.warn("Could not fetch date range:", e);
    }
}

// 6. SYNC TALLY LEDGERS (OPENS SYNC MODAL)
function syncAcctTallyLedgers() {
    openAcctSyncModal();
}

// 7. RENDER HSN SPARES MAPPING GRID (MATCHED TO TAX RATES GRID)
function renderAcctHsnMappingGrid(hsnList) {
    const container = document.getElementById("acct-hsn-mapping-list");
    const badge = document.getElementById("acct-hsn-count-badge");
    if (!container) return;
    container.innerHTML = "";

    if (badge) badge.textContent = `${hsnList.length} HSN Codes Detected`;

    hsnList.forEach(item => {
        const colDiv = document.createElement("div");
        colDiv.style.display = "flex";
        colDiv.style.flexDirection = "column";
        colDiv.style.gap = "6px";
        colDiv.style.minWidth = "220px";
        colDiv.style.flex = "1";

        const labelDiv = document.createElement("div");
        labelDiv.style.display = "flex";
        labelDiv.style.justifyContent = "space-between";
        labelDiv.style.alignItems = "center";

        const label = document.createElement("label");
        label.style.fontSize = "0.85rem";
        label.style.fontWeight = "600";
        label.style.color = "var(--text-muted)";
        label.innerHTML = `HSN <strong>${item.hsn_code}</strong> (${item.gst_rate}% GST):`;

        const amountBadge = document.createElement("span");
        amountBadge.style.fontSize = "0.78rem";
        amountBadge.style.fontWeight = "700";
        amountBadge.style.color = "var(--brand-primary)";
        amountBadge.style.fontFamily = "var(--font-mono)";
        amountBadge.textContent = `₹ ${Number(item.total_price).toLocaleString('en-IN', {minimumFractionDigits: 2})}`;

        labelDiv.appendChild(label);
        labelDiv.appendChild(amountBadge);

        const wrapper = document.createElement("div");
        wrapper.className = "select-wrapper";

        const select = document.createElement("select");
        select.className = "acct-hsn-select";
        select.setAttribute("data-hsn-key", `${item.hsn_code}_${item.gst_rate}`);
        select.setAttribute("data-hsn-code", item.hsn_code);

        // Populate options ONLY with actual Tally ledgers (No default synthetic target)
        let optionsHtml = `<option value="">-- Not Mapped --</option>`;
        if (AccountingState.availableLedgers && AccountingState.availableLedgers.length > 0) {
            AccountingState.availableLedgers.forEach(l => {
                const isSelected = (item.is_matched && item.matched_ledger && l.toLowerCase() === item.matched_ledger.toLowerCase()) ? "selected" : "";
                optionsHtml += `<option value="${l}" ${isSelected}>${l}</option>`;
            });
        }
        select.innerHTML = optionsHtml;
        wrapper.appendChild(select);

        // Status row with dynamic badge and row count
        const statusRow = document.createElement("div");
        statusRow.style.display = "flex";
        statusRow.style.justifyContent = "space-between";
        statusRow.style.alignItems = "center";
        statusRow.style.marginTop = "2px";

        const statusTag = document.createElement("span");
        const isMatched = item.is_matched && Boolean(item.matched_ledger);
        statusTag.style.cssText = isMatched 
            ? "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;"
            : "background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;";
        statusTag.textContent = isMatched ? "✓ Matched in Tally" : "⚠️ Not Mapped";

        const countTag = document.createElement("span");
        countTag.style.fontSize = "0.72rem";
        countTag.style.color = "var(--text-muted)";
        countTag.style.fontFamily = "var(--font-mono)";
        countTag.textContent = `${item.rows_count} rows`;

        statusRow.appendChild(statusTag);
        statusRow.appendChild(countTag);

        select.addEventListener("change", (e) => {
            if (e.target.value) {
                statusTag.style.cssText = "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;";
                statusTag.textContent = "✓ Selected";
            } else {
                statusTag.style.cssText = "background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px;";
                statusTag.textContent = "⚠️ Not Mapped";
            }
        });

        colDiv.appendChild(labelDiv);
        colDiv.appendChild(wrapper);
        colDiv.appendChild(statusRow);
        container.appendChild(colDiv);
    });
}

// 8. RENDER TAXES GRID (MATCHED TO CARD 5)
function renderAcctTaxesMappingGrid(taxesList) {
    const container = document.getElementById("acct-tax-mapping-list");
    if (!container) return;
    container.innerHTML = "";

    taxesList.forEach(t => {
        const colDiv = document.createElement("div");
        colDiv.style.display = "flex";
        colDiv.style.flexDirection = "column";
        colDiv.style.gap = "6px";
        colDiv.style.minWidth = "220px";
        colDiv.style.flex = "1";

        const label = document.createElement("label");
        label.style.fontSize = "0.85rem";
        label.style.fontWeight = "600";
        label.style.color = "var(--text-muted)";
        label.innerText = `${t.tax_key} Ledger in Tally:`;

        const wrapper = document.createElement("div");
        wrapper.className = "select-wrapper";

        const select = document.createElement("select");
        select.className = "acct-tax-select";
        select.setAttribute("data-tax-key", t.tax_key);

        let optionsHtml = `<option value="">-- Not Mapped --</option>`;
        if (AccountingState.availableLedgers && AccountingState.availableLedgers.length > 0) {
            AccountingState.availableLedgers.forEach(l => {
                const isSelected = (t.is_matched && t.matched_ledger && l.toLowerCase() === t.matched_ledger.toLowerCase()) ? "selected" : "";
                optionsHtml += `<option value="${l}" ${isSelected}>${l}</option>`;
            });
        }
        select.innerHTML = optionsHtml;
        wrapper.appendChild(select);

        const isMatched = t.is_matched && Boolean(t.matched_ledger);
        const statusTag = document.createElement("span");
        statusTag.style.cssText = isMatched 
            ? "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; align-self: flex-start; margin-top: 2px;"
            : "background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; align-self: flex-start; margin-top: 2px;";
        statusTag.textContent = isMatched ? "✓ Matched in Tally" : "⚠️ Not Mapped";

        select.addEventListener("change", (e) => {
            if (e.target.value) {
                statusTag.style.cssText = "background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; align-self: flex-start; margin-top: 2px;";
                statusTag.textContent = "✓ Selected";
            } else {
                statusTag.style.cssText = "background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.72rem; padding: 2px 6px; border-radius: 4px; align-self: flex-start; margin-top: 2px;";
                statusTag.textContent = "⚠️ Not Mapped";
            }
        });

        colDiv.appendChild(label);
        colDiv.appendChild(wrapper);
        colDiv.appendChild(statusTag);
        container.appendChild(colDiv);
    });
}

function populateAcctDropdowns(matchedMisc, suggestedParty) {
    // 1. Misc Ledger Dropdown
    const miscSelect = document.getElementById("acct_misc_ledger");
    if (miscSelect) {
        miscSelect.innerHTML = `<option value="">-- Choose Misc Ledger --</option>`;
        if (AccountingState.availableLedgers && AccountingState.availableLedgers.length > 0) {
            let miscSelected = false;
            AccountingState.availableLedgers.forEach(l => {
                const isSelected = (matchedMisc && l.toLowerCase() === matchedMisc.toLowerCase()) ? "selected" : "";
                if (isSelected) miscSelected = true;
                miscSelect.innerHTML += `<option value="${l}" ${isSelected}>${l}</option>`;
            });
            // If matchedMisc not selected, check if "Misc Exp" is present in Tally ledgers
            if (!miscSelected) {
                for (let opt of miscSelect.options) {
                    if (opt.value.toLowerCase() === "misc exp") {
                        opt.selected = true;
                        break;
                    }
                }
            }
        } else {
            miscSelect.innerHTML = `<option value="">-- Sync Tally to load ledgers --</option>`;
        }
    }

    // 2. Party Ledger Dropdown
    const partySelect = document.getElementById("acct_party_name");
    if (partySelect) {
        partySelect.innerHTML = `<option value="">-- Choose Party Ledger from Tally --</option>`;
        if (AccountingState.availableLedgers && AccountingState.availableLedgers.length > 0) {
            AccountingState.availableLedgers.forEach(l => {
                const isSelected = (suggestedParty && l.toLowerCase() === suggestedParty.toLowerCase()) ? "selected" : "";
                partySelect.innerHTML += `<option value="${l}" ${isSelected}>${l}</option>`;
            });
        }
        onAcctPartyChanged();
    }
}

function onAcctPartyChanged() {
    const partySelect = document.getElementById("acct_party_name");
    const buyerInput = document.getElementById("acct_buyer_name");
    if (partySelect && buyerInput && partySelect.value) {
        buyerInput.value = partySelect.value;
    }
}

// 9. GENERATE ACCOUNTING XML
async function generateAcctXml() {
    if (!AccountingState.fileId) {
        alert("Please upload a spares Excel file first");
        return;
    }

    const companyName = (document.getElementById("acct_company_select")?.value || AccountingState.tallyCompany || "").trim();
    const voucherType = (document.getElementById("acct_voucher_type")?.value || "Sales").trim();
    const partyName = (document.getElementById("acct_party_name")?.value || "").trim();

    if (!companyName) {
        alert("Tally Company Name is required");
        return;
    }
    if (!partyName) {
        alert("Please select Party A/c Name from Tally ledgers");
        return;
    }

    // Collect HSN mappings
    const hsnMappings = {};
    const unmappedHsn = [];
    document.querySelectorAll(".acct-hsn-select").forEach(sel => {
        const key = sel.getAttribute("data-hsn-key");
        if (sel.value) {
            hsnMappings[key] = sel.value;
        } else {
            unmappedHsn.push(sel.getAttribute("data-hsn-code") || key);
        }
    });

    if (unmappedHsn.length > 0) {
        const proceed = confirm(`⚠️ Warning: ${unmappedHsn.length} HSN code(s) (${unmappedHsn.join(', ')}) are currently '-- Not Mapped --'.\n\nDo you want to proceed anyway with default ledger names?`);
        if (!proceed) return;
    }

    // Collect Tax mappings
    const taxMappings = {};
    document.querySelectorAll(".acct-tax-select").forEach(sel => {
        const key = sel.getAttribute("data-tax-key");
        if (sel.value) {
            taxMappings[key] = sel.value;
        }
    });

    const miscLrg = document.getElementById("acct_misc_ledger")?.value || "Misc Exp";
    const narrationPrefix = document.getElementById("acct_narration_prefix")?.value || "GST Invoice Number :: ";

    const partyDetails = {
        buyer_name: document.getElementById("acct_buyer_name")?.value || partyName,
        state: document.getElementById("acct_state")?.value || "Andhra Pradesh",
        place_of_supply: document.getElementById("acct_pos")?.value || "Andhra Pradesh",
        country: document.getElementById("acct_country")?.value || "India",
        registration_type: document.getElementById("acct_reg_type")?.value || "Unregistered/Consumer",
        gstin: document.getElementById("acct_gstin")?.value || ""
    };

    const loader = document.getElementById("acct-gen-loader");
    const btnLabel = document.getElementById("acct-gen-btn-label");
    const btn = document.getElementById("btn-acct-generate-xml");

    if (btn) btn.disabled = true;
    if (loader) loader.style.display = "inline-block";
    if (btnLabel) btnLabel.textContent = "Generating XML...";

    const verifContainer = document.getElementById("acct-verification-container");
    if (verifContainer) verifContainer.style.display = "none";

    try {
        const res = await fetch("/api/accounting/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: AccountingState.fileId,
                sheet_name: AccountingState.currentSheet,
                column_mappings: AccountingState.columnMappings,
                original_filename: AccountingState.filename,
                company_name: companyName,
                voucher_type: voucherType,
                party_name: partyName,
                party_details: partyDetails,
                hsn_ledger_mappings: hsnMappings,
                tax_ledger_mappings: taxMappings,
                misc_ledger_name: miscLrg,
                narration_prefix: narrationPrefix,
                from_date: document.getElementById("acct-filter-from-date")?.value || null,
                to_date: document.getElementById("acct-filter-to-date")?.value || null
            })
        });

        const data = await res.json();
        if (!data.success) {
            alert("XML Generation Error: " + (data.error || "Unknown"));
            return;
        }

        AccountingState.generatedXmlFilename = data.filename;
        const audit = data.audit_summary || {};

        // 1. Header Badges
        const vchBadge = document.getElementById("acct-verif-vch-badge");
        if (vchBadge) vchBadge.textContent = `${(data.voucher_count || 0).toLocaleString()} Vouchers`;
        const fnBadge = document.getElementById("acct-verif-filename-badge");
        if (fnBadge) fnBadge.textContent = data.filename;

        // 2. Left Table: Distinct HSN Codes Breakdown
        const hsnTbody = document.getElementById("acct-verif-hsn-tbody");
        if (hsnTbody) {
            hsnTbody.innerHTML = "";
            const hsnList = audit.hsn_breakdown || [];
            if (hsnList.length > 0) {
                hsnList.forEach(item => {
                    const row = document.createElement("tr");
                    row.innerHTML = `
                        <td style="text-align: left; padding: 10px 12px; font-weight: 600;">${item.hsn_code}</td>
                        <td style="text-align: right; padding: 10px 12px;">${Number(item.rows_count).toLocaleString()}</td>
                        <td style="text-align: right; padding: 10px 12px; color: var(--accent-blue); font-weight: 600;">₹ ${Number(item.total_price).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                    `;
                    hsnTbody.appendChild(row);
                });
            } else {
                hsnTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 15px;">No HSN breakdown available</td></tr>`;
            }
        }
        const hsnDistinctCount = document.getElementById("acct-hsn-distinct-count");
        if (hsnDistinctCount) hsnDistinctCount.textContent = `${(audit.hsn_breakdown || []).length} Distinct HSN Codes`;
        const hsnTotalRows = document.getElementById("acct-hsn-total-rows");
        if (hsnTotalRows) hsnTotalRows.textContent = `${(audit.total_rows || 0).toLocaleString()} Rows`;
        const hsnTotalTaxable = document.getElementById("acct-hsn-total-taxable");
        if (hsnTotalTaxable) hsnTotalTaxable.textContent = `₹ ${Number(audit.total_selling_price || 0).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        // 3. Right Table: GST Taxes & Misc Breakdown
        const taxTbody = document.getElementById("acct-verif-tax-tbody");
        const miscVal = Number(audit.misc_offset || 0);
        if (taxTbody) {
            taxTbody.innerHTML = "";
            const taxList = audit.tax_breakdown || [];
            taxList.forEach(t => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td style="text-align: left; padding: 10px 12px; font-weight: 600;">${t.tax_type} (${t.rate})</td>
                    <td style="text-align: center; padding: 10px 12px;"><span class="badge" style="background: rgba(16,185,129,0.15); color: var(--brand-primary);">${t.rate}</span></td>
                    <td style="text-align: right; padding: 10px 12px; color: var(--brand-primary); font-weight: 600;">₹ ${Number(t.total_tax).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                `;
                taxTbody.appendChild(row);
            });

            // Add Misc / Round-off entry (supports positive or negative)
            const miscLrgName = audit.misc_ledger_name || 'Misc Exp';
            const miscSign = miscVal >= 0 ? '+' : '-';
            const miscColor = miscVal >= 0 ? 'var(--brand-primary)' : '#f87171';
            const miscRow = document.createElement("tr");
            miscRow.innerHTML = `
                <td style="text-align: left; padding: 10px 12px; font-weight: 600; color: var(--text-muted);">Misc / Round-off (${miscLrgName})</td>
                <td style="text-align: center; padding: 10px 12px; color: var(--text-muted);">—</td>
                <td style="text-align: right; padding: 10px 12px; font-weight: 600; color: ${miscColor};">${miscSign}₹ ${Math.abs(miscVal).toFixed(2)}</td>
            `;
            taxTbody.appendChild(miscRow);
        }
        const taxHeadsCount = document.getElementById("acct-tax-heads-count");
        if (taxHeadsCount) taxHeadsCount.textContent = `${(audit.tax_breakdown || []).length} Tax Heads + Misc`;
        const taxTotalVal = document.getElementById("acct-tax-total-val");
        const totalTaxesAndMisc = (audit.total_cgst || 0) + (audit.total_sgst || 0) + (audit.total_igst || 0) + miscVal;
        if (taxTotalVal) taxTotalVal.textContent = `₹ ${Number(totalTaxesAndMisc).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        // 4. Equation Reconciliation Bar
        const eqEl = document.getElementById("acct-verif-equation-container");
        if (eqEl) {
            const miscSign = miscVal >= 0 ? '+' : '-';
            eqEl.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; color: var(--text-muted);">Total Selling Price:</span>
                    <strong style="color: var(--accent-blue); font-size: 0.95rem;">₹ ${Number(audit.total_selling_price || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>
                </div>
                <span style="color: var(--text-muted); font-size: 1.1rem; font-weight: 700;">+</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; color: var(--text-muted);">CGST:</span>
                    <strong style="color: var(--brand-primary); font-size: 0.95rem;">₹ ${Number(audit.total_cgst || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>
                </div>
                <span style="color: var(--text-muted); font-size: 1.1rem; font-weight: 700;">+</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; color: var(--text-muted);">SGST:</span>
                    <strong style="color: var(--brand-primary); font-size: 0.95rem;">₹ ${Number(audit.total_sgst || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>
                </div>
                ${audit.total_igst > 0 ? `
                <span style="color: var(--text-muted); font-size: 1.1rem; font-weight: 700;">+</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; color: var(--text-muted);">IGST:</span>
                    <strong style="color: var(--brand-primary); font-size: 0.95rem;">₹ ${Number(audit.total_igst || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>
                </div>` : ''}
                <span style="color: var(--text-muted); font-size: 1.1rem; font-weight: 700;">${miscSign}</span>
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 0.8rem; color: var(--text-muted);">Misc:</span>
                    <strong style="color: ${miscVal >= 0 ? 'var(--brand-primary)' : '#f87171'}; font-size: 0.95rem;">₹ ${Math.abs(miscVal).toFixed(2)}</strong>
                </div>
                <span style="color: var(--text-muted); font-size: 1.3rem; font-weight: 700;">=</span>
                <div style="display: flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4); padding: 8px 16px; border-radius: var(--radius-md);">
                    <span style="font-size: 0.82rem; color: #ffffff; font-weight: 700;">Grand Total:</span>
                    <strong style="color: #ffffff; font-size: 1.15rem; font-weight: 800;">₹ ${Number(audit.grand_total || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong>
                </div>
            `;
        }

        // 5. Display Verification Container
        const verifContainer = document.getElementById("acct-verification-container");
        if (verifContainer) {
            verifContainer.style.display = "block";
            verifContainer.scrollIntoView({ behavior: "smooth" });
        }

    } catch (e) {
        alert("Generate request failed: " + e.message);
    } finally {
        if (btn) btn.disabled = false;
        if (loader) loader.style.display = "none";
        if (btnLabel) btnLabel.textContent = "Generate Accounting Vouchers XML";
    }
}

// 10. GENERATE PROCESSED EXCEL SUMMARY
async function generateAcctExcel() {
    if (!AccountingState.fileId) {
        alert("Please upload a spares Excel file first");
        return;
    }

    const partyName = (document.getElementById("acct_party_name")?.value || "").trim();
    if (!partyName) {
        alert("Please select Party A/c Name from Tally ledgers");
        return;
    }

    // Collect HSN mappings
    const hsnMappings = {};
    document.querySelectorAll(".acct-hsn-select").forEach(sel => {
        const key = sel.getAttribute("data-hsn-key");
        if (sel.value) {
            hsnMappings[key] = sel.value;
        }
    });

    const miscLrg = document.getElementById("acct_misc_ledger")?.value || "Misc Exp";

    const btn = document.getElementById("btn-acct-generate-excel");
    const loader = document.getElementById("acct-excel-loader");
    const btnLabel = document.getElementById("acct-excel-btn-label");

    if (btn) btn.disabled = true;
    if (loader) loader.style.display = "inline-block";
    if (btnLabel) btnLabel.textContent = "Generating Excel...";

    document.getElementById("acct-excel-success-container").style.display = "none";

    try {
        const res = await fetch("/api/accounting/generate-excel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: AccountingState.fileId,
                sheet_name: AccountingState.currentSheet,
                column_mappings: AccountingState.columnMappings,
                original_filename: AccountingState.filename,
                party_name: partyName,
                hsn_ledger_mappings: hsnMappings,
                misc_ledger_name: miscLrg,
                from_date: document.getElementById("acct-filter-from-date")?.value || null,
                to_date: document.getElementById("acct-filter-to-date")?.value || null
            })
        });

        const data = await res.json();
        if (!data.success) {
            alert("Excel Generation Error: " + (data.error || "Unknown"));
            return;
        }

        AccountingState.generatedExcelFilename = data.filename;

        // Display Excel Success Box (Matched exactly to Item Invoice)
        const successBox = document.getElementById("acct-excel-success-container");
        const downloadLink = document.getElementById("acct-excel-download-link");
        if (downloadLink) {
            downloadLink.href = data.download_url;
            downloadLink.onclick = (e) => {
                e.preventDefault();
                triggerAcctFileDownload(data.filename);
            };
        }
        if (successBox) {
            successBox.style.display = "flex";
            successBox.scrollIntoView({ behavior: "smooth" });
        }

    } catch (e) {
        alert("Generate Excel failed: " + e.message);
    } finally {
        if (btn) btn.disabled = false;
        if (loader) loader.style.display = "none";
        if (btnLabel) btnLabel.textContent = "Generate Processed Excel";
    }
}

// 11. DOWNLOAD WITH CUSTOM SAVE LOCATION & FILENAME DIALOG
async function downloadAcctXmlWithSaveDialog() {
    const filename = AccountingState.generatedXmlFilename;
    if (!filename) {
        alert("No generated XML file found. Please generate the XML first.");
        return;
    }

    // 1. Try PyWebView native Save As file dialog (if running inside PyWebView desktop window)
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file_dialog) {
            const res = await window.pywebview.api.save_file_dialog(filename);
            if (res && res.success) {
                alert(`✅ File successfully saved to:\n\n${res.saved_to}`);
                return;
            } else if (res && res.cancelled) {
                return; // User clicked Cancel
            }
        }
    } catch (e) {
        console.warn("PyWebView Save Dialog fallback triggered:", e);
    }

    // 2. Try modern browser File System Access API (showSaveFilePicker)
    // Supported natively in Chrome, Edge, and Chromium browsers
    if (window.showSaveFilePicker) {
        try {
            const handle = await window.showSaveFilePicker({
                suggestedName: filename,
                types: [{
                    description: 'Tally XML File',
                    accept: { 'application/xml': ['.xml'] }
                }]
            });
            const writable = await handle.createWritable();
            const res = await fetch(`/download/${filename}`);
            const blob = await res.blob();
            await writable.write(blob);
            await writable.close();
            alert(`✅ XML file successfully saved!`);
            return;
        } catch (err) {
            if (err.name === 'AbortError') {
                return; // User intentionally clicked Cancel
            }
            console.warn("Browser showSaveFilePicker fallback:", err);
        }
    }

    // 3. Try Backend Native Windows Save As Dialog (Tkinter on host)
    try {
        const res = await fetch("/api/accounting/save-file-dialog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: filename })
        });
        const data = await res.json();
        if (data.success && data.saved_to) {
            alert(`✅ File successfully saved to:\n\n${data.saved_to}`);
            return;
        } else if (data.cancelled) {
            return; // User clicked Cancel in Windows Dialog
        }
    } catch (err) {
        console.warn("Backend save dialog fallback:", err);
    }

    // 4. Fallback: Browser download anchor with suggested filename
    const a = document.createElement("a");
    a.href = `/download/${filename}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// 12. TRIGGER FILE DOWNLOAD (FOR EXCEL OR OTHER FILES)
async function triggerAcctFileDownload(filename) {
    if (!filename) return;

    // 1. PyWebView native Save As file dialog
    try {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.save_file_dialog) {
            const res = await window.pywebview.api.save_file_dialog(filename);
            if (res && res.success) {
                alert(`✅ File successfully saved to:\n\n${res.saved_to}`);
                return;
            } else if (res && res.cancelled) {
                return;
            }
        }
    } catch (e) {
        console.warn("PyWebView Save Dialog fallback triggered:", e);
    }

    // 2. Browser showSaveFilePicker
    if (window.showSaveFilePicker) {
        try {
            const ext = filename.endsWith('.xml') ? '.xml' : (filename.endsWith('.xlsx') ? '.xlsx' : '');
            const types = ext === '.xml' ? [{ description: 'XML File', accept: { 'application/xml': ['.xml'] } }] : [{ description: 'Excel File', accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] } }];
            const handle = await window.showSaveFilePicker({ suggestedName: filename, types });
            const writable = await handle.createWritable();
            const res = await fetch(`/download/${filename}`);
            const blob = await res.blob();
            await writable.write(blob);
            await writable.close();
            alert(`✅ File successfully saved!`);
            return;
        } catch (err) {
            if (err.name === 'AbortError') return;
        }
    }

    // 3. Backend native dialog
    try {
        const res = await fetch("/api/accounting/save-file-dialog", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: filename })
        });
        const data = await res.json();
        if (data.success && data.saved_to) {
            alert(`✅ File successfully saved to:\n\n${data.saved_to}`);
            return;
        } else if (data.cancelled) {
            return;
        }
    } catch (err) {}

    // 4. Browser link fallback
    const a = document.createElement("a");
    a.href = `/download/${filename}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// 13. SAVE ACTIONS FOR EXCEL
async function saveAcctExcelToDownloads() {
    if (!AccountingState.generatedExcelFilename) {
        alert("No generated Excel file found");
        return;
    }
    triggerAcctFileDownload(AccountingState.generatedExcelFilename);
}


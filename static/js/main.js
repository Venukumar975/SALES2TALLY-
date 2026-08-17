// Main Application Entry Point & DOM Event Wiring

document.addEventListener("DOMContentLoaded", () => {
    checkLicenseHealth();
    setInterval(checkLicenseHealth, 5000);
    loadSyncedCompanies();

    // Drag and drop event handlers
    const dropzone = document.getElementById("dropzone");
    const excelInput = document.getElementById("excel_file");

    if (dropzone && excelInput) {
        ["dragenter", "dragover"].forEach(eventName => {
            dropzone.addEventListener(eventName, e => {
                e.preventDefault();
                dropzone.classList.add("dragover");
            }, false);
        });

        ["dragleave", "drop"].forEach(eventName => {
            dropzone.addEventListener(eventName, e => {
                e.preventDefault();
                dropzone.classList.remove("dragover");
            }, false);
        });

        dropzone.addEventListener("drop", e => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                excelInput.files = files;
                handleFileSelected();
            }
        });

        excelInput.addEventListener("change", handleFileSelected);
    }

    // Sheet select and Header Row change handlers
    const sheetSelect = document.getElementById("sheet_select");
    if (sheetSelect) {
        sheetSelect.addEventListener("change", (e) => {
            const sheet = e.target.value;
            if (sheet) {
                analyzeSheet(sheet);
            } else {
                document.getElementById("card-mapping").style.display = "none";
                document.getElementById("card-tally").style.display = "none";
                document.getElementById("card-generate").style.display = "none";
            }
        });
    }

    const headerRowInput = document.getElementById("header_row");
    if (headerRowInput) {
        headerRowInput.addEventListener("change", () => {
            const sheet = document.getElementById("sheet_select").value;
            if (sheet) {
                analyzeSheet(sheet);
            }
        });
    }
    
    // Modal Elements
    const ledgersModal = document.getElementById("sync-ledgers-modal");
    const stockModal = document.getElementById("sync-stock-modal");
    const createItemsModal = document.getElementById("create-stock-items-modal");
    
    // Modal Open Triggers
    const btnOpenLedgers = document.getElementById("btn-open-sync-ledgers-modal");
    if (btnOpenLedgers) {
        btnOpenLedgers.addEventListener("click", () => {
            ledgersModal.style.display = "block";
        });
    }

    const btnOpenStock = document.getElementById("btn-open-sync-stock-modal");
    if (btnOpenStock) {
        btnOpenStock.addEventListener("click", () => {
            stockModal.style.display = "block";
        });
    }
    
    // Modal Close Triggers (Ledgers)
    const closeLedgersX = document.getElementById("close-ledgers-modal-x");
    if (closeLedgersX) closeLedgersX.addEventListener("click", () => ledgersModal.style.display = "none");
    const closeLedgersBtn = document.getElementById("close-ledgers-modal-btn");
    if (closeLedgersBtn) closeLedgersBtn.addEventListener("click", () => ledgersModal.style.display = "none");
    
    // Modal Close Triggers (Stock)
    const closeStockX = document.getElementById("close-stock-modal-x");
    if (closeStockX) closeStockX.addEventListener("click", () => stockModal.style.display = "none");
    const closeStockBtn = document.getElementById("close-stock-modal-btn");
    if (closeStockBtn) closeStockBtn.addEventListener("click", () => stockModal.style.display = "none");

    // Modal Close Triggers (Create Stock Items)
    const closeCreateItemsX = document.getElementById("close-create-items-modal-x");
    if (closeCreateItemsX) closeCreateItemsX.addEventListener("click", () => createItemsModal.style.display = "none");
    const closeCreateItemsBtn = document.getElementById("close-create-items-modal-btn");
    if (closeCreateItemsBtn) closeCreateItemsBtn.addEventListener("click", () => createItemsModal.style.display = "none");
    
    // Sync action buttons click handlers
    const btnSyncLedgers = document.getElementById("btn-sync-ledgers-action");
    if (btnSyncLedgers) btnSyncLedgers.addEventListener("click", () => syncTally("ledgers"));
    const btnSyncStock = document.getElementById("btn-sync-stock-action");
    if (btnSyncStock) btnSyncStock.addEventListener("click", () => syncTally("stock"));
    
    // Create missing ledgers & items click handlers
    const btnCreateLedgers = document.getElementById("btn-create-tally-ledgers");
    if (btnCreateLedgers) btnCreateLedgers.addEventListener("click", () => createTallyLedgers());
    const btnCreateItems = document.getElementById("btn-create-tally-items");
    if (btnCreateItems) btnCreateItems.addEventListener("click", () => openCreateItemsModal());
    const btnGenerateXml = document.getElementById("btn-generate-xml");
    if (btnGenerateXml) btnGenerateXml.addEventListener("click", () => generateSalesXML());
    const btnGenerateExcel = document.getElementById("btn-generate-excel");
    if (btnGenerateExcel) btnGenerateExcel.addEventListener("click", () => generateProcessedExcel());

    const tallyLedgerCompanySelect = document.getElementById("tally_ledger_company_select");
    if (tallyLedgerCompanySelect) {
        tallyLedgerCompanySelect.addEventListener("change", (e) => {
            loadLedgersForVoucherConfig(e.target.value);
        });
    }
    
    // Close modal when clicking outside
    window.addEventListener("click", (e) => {
        if (e.target === ledgersModal) ledgersModal.style.display = "none";
        if (e.target === stockModal) stockModal.style.display = "none";
        if (e.target === createItemsModal) createItemsModal.style.display = "none";
    });
});

async function checkLicenseHealth() {
    try {
        const res = await fetch("/api/license/status");
        const data = await res.json();
        const pill = document.getElementById("header-license-pill");
        const text = document.getElementById("header-license-text");
        
        if (!pill || !text) return;
        
        if (!data.is_valid) {
            window.location.href = "/login";
            return;
        }
        
        if (data.type === "LIFETIME") {
            text.innerText = "Lifetime Active";
            pill.style.borderColor = "rgba(16, 185, 129, 0.4)";
            pill.style.color = "#34d399";
        } else {
            const mins = Math.ceil((data.remaining_seconds || 0) / 60);
            text.innerText = `${data.type} (${mins}m remaining)`;
            if (mins <= 5) {
                pill.style.borderColor = "rgba(239, 68, 68, 0.4)";
                pill.style.color = "#f87171";
            }
        }
    } catch (e) {
        console.error("License check error:", e);
    }
}


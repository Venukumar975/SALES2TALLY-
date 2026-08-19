// Tally Prime Sync & Company Profile Management

async function loadSyncedCompanies() {
    try {
        const res = await fetch("/api/tally/companies");
        const data = await res.json();
        if (data.success) {
            const ledgerSelect = document.getElementById("tally_ledger_company_select");
            const stockSelect = document.getElementById("tally_stock_company_select");
            
            const currentLedger = ledgerSelect.value;
            const currentStock = stockSelect.value;
            
            ledgerSelect.innerHTML = '<option value="">-- Select Synced Company --</option>';
            stockSelect.innerHTML = '<option value="">-- Select Synced Company --</option>';
            
            data.companies.forEach(co => {
                if (co.has_ledgers) {
                    const opt = document.createElement("option");
                    opt.value = co.display_name;
                    opt.innerText = `${co.display_name} (Sync: ${co.ledger_last_sync} - ${co.ledger_count} Ledgers)`;
                    ledgerSelect.appendChild(opt);
                }
                if (co.has_stock) {
                    const opt = document.createElement("option");
                    opt.value = co.display_name;
                    opt.innerText = `${co.display_name} (Sync: ${co.stock_last_sync} - ${co.stock_count} Items)`;
                    stockSelect.appendChild(opt);
                }
            });
            
            if (currentLedger) ledgerSelect.value = currentLedger;
            if (currentStock) stockSelect.value = currentStock;
            
            if (ledgerSelect.value) {
                loadLedgersForVoucherConfig(ledgerSelect.value);
            }
        }
    } catch (err) {
        console.error("Failed to load synced companies:", err);
    }
}

async function syncTally(type) {
    const modalId = type === "ledgers" ? "sync-ledgers-modal" : "sync-stock-modal";
    const inputId = type === "ledgers" ? "sync_ledger_company_name" : "sync_stock_company_name";
    const selectId = type === "ledgers" ? "tally_ledger_company_select" : "tally_stock_company_select";
    
    const newCoInput = document.getElementById(inputId);
    const companyName = newCoInput.value.trim();
    
    if (!companyName) {
        alert("Please enter the Company Name exactly as saved in Tally.");
        return;
    }
    
    const startSyncBtn = type === "ledgers" ? document.getElementById("btn-sync-ledgers-action") : document.getElementById("btn-sync-stock-action");
    startSyncBtn.disabled = true;
    
    const apiEndpoint = type === "ledgers" ? "/api/tally/sync" : "/api/tally/sync-stock";
    const typeLabel = type === "ledgers" ? "accounting ledgers" : "inventory stock items";
    const loaderId = type === "ledgers" ? "ledgers-loader" : "stock-loader";
    
    showStatus("tally-sync-status", loaderId, `Connecting to Tally on port 9000 to sync ${typeLabel} for '${companyName}'...`, "info");
    
    try {
        const res = await fetch(apiEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name: companyName })
        });
        const data = await res.json();
        
        if (data.success) {
            showStatus("tally-sync-status", null, `✓ Successfully synced ${data.count} ${typeLabel} for '${data.company_name}'!`, "success");
            newCoInput.value = "";
            
            document.getElementById(modalId).style.display = "none";
            
            await loadSyncedCompanies();
            
            document.getElementById(selectId).value = data.company_name;
            if (type === "ledgers") {
                loadLedgersForVoucherConfig(data.company_name);
            }
        } else {
            document.getElementById(modalId).style.display = "none";
            showStatus("tally-sync-status", null, `❌ Sync Failed: ${data.error}`, "error");
        }
    } catch (err) {
        document.getElementById(modalId).style.display = "none";
        showStatus("tally-sync-status", null, `❌ Network Error: ${err.message}`, "error");
    } finally {
        startSyncBtn.disabled = false;
    }
}

async function loadLedgersForVoucherConfig(companyName) {
    const miscSelect = document.getElementById("misc_ledger_select");
    const xmlCompanyInput = document.getElementById("xml_company_name");
    
    miscSelect.innerHTML = '<option value="">-- Choose Misc Ledger --</option>';
    tallyLedgerList = [];
    
    if (!companyName) return;
    xmlCompanyInput.value = companyName;
    
    try {
        const res = await fetch("/api/tally/ledgers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ company_name: companyName })
        });
        const data = await res.json();
        
        if (data.success && data.ledgers) {
            tallyLedgerList = data.ledgers;
            let defaultMisc = "";
            
            data.ledgers.forEach(ledger => {
                const optMisc = document.createElement("option");
                optMisc.value = ledger;
                optMisc.innerText = ledger;
                miscSelect.appendChild(optMisc);
                
                const lowerLedger = ledger.toLowerCase();
                if (!defaultMisc && (lowerLedger.includes("misc") || lowerLedger.includes("round") || lowerLedger.includes("conversion"))) {
                    defaultMisc = ledger;
                }
            });
            
            if (defaultMisc) miscSelect.value = defaultMisc;
            
            detectAndRenderTaxRates();
        }
    } catch (err) {
        console.error("Failed to load ledgers for voucher config dropdowns:", err);
    }
}

async function detectAndRenderTaxRates() {
    const sheetSelect = document.getElementById("sheet_select");
    if (!sheetSelect) return;
    const sheet = sheetSelect.value;
    const rowVal = document.getElementById("header_row").value || 1;
    const taxContainer = document.getElementById("detected-tax-rates-container");
    const taxListDiv = document.getElementById("tax-rates-mapping-list");
    const salesContainer = document.getElementById("detected-sales-ledgers-container");
    const salesListDiv = document.getElementById("sales-ledgers-mapping-list");
    
    if (!tempFileId || !sheet) {
        if (taxContainer) taxContainer.style.display = "none";
        if (salesContainer) salesContainer.style.display = "none";
        return;
    }
    
    const mappings = {};
    let hasTaxes = false;
    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
            if (field.id.includes("CGST") || field.id.includes("SGST") || field.id.includes("IGST")) {
                hasTaxes = true;
            }
        }
    });
    
    if (!hasTaxes || !mappings["Taxable Amount"]) {
        if (taxContainer) taxContainer.style.display = "none";
        if (salesContainer) salesContainer.style.display = "none";
        return;
    }
    
    try {
        const res = await fetch("/api/detect-tax-rates", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                header_row: rowVal
            })
        });
        const data = await res.json();
        
        // 1. Render Product Sales Ledgers by Tax Rate
        if (data.success && data.product_rates && data.product_rates.length > 0 && salesContainer && salesListDiv) {
            salesContainer.style.display = "flex";
            salesListDiv.innerHTML = "";
            
            data.product_rates.forEach(rate => {
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
                label.innerText = rate > 0 ? `Product Sales Ledger (${rate}% GST):` : `Product Sales Ledger (0% / Nil Rated):`;
                
                const wrapper = document.createElement("div");
                wrapper.className = "select-wrapper";
                
                const select = document.createElement("select");
                select.className = "sales-rate-mapping-dropdown";
                select.setAttribute("data-sales-rate", `${rate}`);
                select.innerHTML = '<option value="">-- Choose Sales Ledger --</option>';
                
                tallyLedgerList.forEach(ledger => {
                    const opt = document.createElement("option");
                    opt.value = ledger;
                    opt.innerText = ledger;
                    select.appendChild(opt);
                });
                
                // Smart auto-matching for sales ledger based on rate
                let foundMatch = "";
                const rateStr = `${rate}`;
                
                if (rate > 0) {
                    for (let l of tallyLedgerList) {
                        const lLower = l.toLowerCase();
                        if (lLower.includes("sales") && (lLower.includes(`${rateStr}%`) || lLower.includes(` ${rateStr}`))) {
                            foundMatch = l;
                            break;
                        }
                    }
                    if (!foundMatch && rate === 18) {
                        for (let l of tallyLedgerList) {
                            const lLower = l.toLowerCase();
                            if (lLower === "goods sales" || lLower === "sales" || lLower === "sales account") {
                                foundMatch = l;
                                break;
                            }
                        }
                    }
                } else {
                    for (let l of tallyLedgerList) {
                        const lLower = l.toLowerCase();
                        if (lLower.includes("sales") && (lLower.includes("nil") || lLower.includes("exempt") || lLower.includes("0%"))) {
                            foundMatch = l;
                            break;
                        }
                    }
                }
                
                if (!foundMatch) {
                    for (let l of tallyLedgerList) {
                        const lLower = l.toLowerCase();
                        if (lLower.includes("sales")) {
                            foundMatch = l;
                            break;
                        }
                    }
                }
                
                if (foundMatch) {
                    select.value = foundMatch;
                }
                
                wrapper.appendChild(select);
                colDiv.appendChild(label);
                colDiv.appendChild(wrapper);
                salesListDiv.appendChild(colDiv);
            });
        } else if (salesContainer) {
            salesContainer.style.display = "none";
        }

        // 2. Render Duties & Taxes (CGST / SGST / IGST)
        if (data.success && data.tax_keys && data.tax_keys.length > 0 && taxContainer && taxListDiv) {
            detectedTaxKeys = data.tax_keys;
            taxContainer.style.display = "flex";
            
            taxListDiv.innerHTML = "";
            data.tax_keys.forEach(key => {
                const colDiv = document.createElement("div");
                colDiv.style.display = "flex";
                colDiv.style.flexDirection = "column";
                colDiv.style.gap = "6px";
                colDiv.style.minWidth = "200px";
                colDiv.style.flex = "1";
                
                const label = document.createElement("label");
                label.style.fontSize = "0.85rem";
                label.style.fontWeight = "600";
                label.style.color = "var(--text-muted)";
                label.innerText = `${key}:`;
                
                const wrapper = document.createElement("div");
                wrapper.className = "select-wrapper";
                
                const select = document.createElement("select");
                select.className = "tax-rate-mapping-dropdown";
                select.setAttribute("data-tax-key", key);
                select.innerHTML = '<option value="">-- Choose Ledger --</option>';
                
                tallyLedgerList.forEach(ledger => {
                    const opt = document.createElement("option");
                    opt.value = ledger;
                    opt.innerText = ledger;
                    select.appendChild(opt);
                });
                
                const keyLower = key.toLowerCase();
                let foundMatch = "";
                
                const matchType = keyLower.split(" ")[0];
                const matchRateStr = keyLower.split(" ").pop().replace("%", "");
                
                for (let l of tallyLedgerList) {
                    const lLower = l.toLowerCase();
                    if (lLower.includes(matchType) && (lLower.includes(`${matchRateStr}%`) || lLower.includes(` ${matchRateStr}`))) {
                        foundMatch = l;
                        break;
                    }
                }
                
                if (!foundMatch) {
                    for (let l of tallyLedgerList) {
                        if (l.toLowerCase().includes(matchType)) {
                            foundMatch = l;
                            break;
                        }
                    }
                }
                
                if (foundMatch) {
                    select.value = foundMatch;
                }
                
                wrapper.appendChild(select);
                colDiv.appendChild(label);
                colDiv.appendChild(wrapper);
                taxListDiv.appendChild(colDiv);
            });
        } else if (taxContainer) {
            taxContainer.style.display = "none";
        }
    } catch (err) {
        console.error("Error detecting tax and sales rates:", err);
        if (taxContainer) taxContainer.style.display = "none";
        if (salesContainer) salesContainer.style.display = "none";
    }
}

// Party & Product Verification and Master Creation Modals

let lastDetectedUnits = [];

function switchVerificationView(activeViewId) {
    const views = [
        "party-check-results-container",
        "product-check-results-container",
        "units-check-results-container"
    ];
    views.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.style.display = (id === activeViewId) ? "flex" : "none";
        }
    });
}

async function checkPartyNames() {
    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    if (!tempFileId) {
        showStatus("mapping-status", null, "⚠️ Please upload an Excel workbook first.", "error");
        return;
    }
    if (!sheet) {
        showStatus("mapping-status", null, "⚠️ Please select a worksheet sheet first.", "error");
        return;
    }

    const mappings = {};
    let mappingValid = true;

    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        } else if (field.required) {
            mappingValid = false;
        }
    });

    if (!mappingValid) {
        showStatus("mapping-status", null, "⚠️ Please map all required columns before checking.", "error");
        return;
    }

    const ledgerCo = document.getElementById("tally_ledger_company_select").value;
    if (!ledgerCo) {
        showStatus("mapping-status", null, "⚠️ Please select/sync a Tally Ledger Company. This is required for party checking.", "error");
        return;
    }

    showStatus("mapping-status", "check-parties-loader", "Checking party names against Tally ledgers...", "info");
    document.getElementById("btn-check-parties").disabled = true;

    const fromDate = document.getElementById("filter-from-date").value;
    const toDate = document.getElementById("filter-to-date").value;

    try {
        const res = await fetch("/api/check-parties", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                ledger_company: ledgerCo,
                from_date: fromDate,
                to_date: toDate,
                header_row: rowVal
            })
        });
        
        const data = await res.json();

        if (data.success) {
            hideStatus("mapping-status");
            switchVerificationView("party-check-results-container");

                        // 1. Perfect matches -> Isolated clean single card with 100% Match badge
            document.getElementById("count-perfect").innerText = data.perfect_matches.length;
            const listPerf = document.getElementById("list-perfect");
            const sectFuzzy = document.getElementById("section-fuzzy-parties");
            listPerf.innerHTML = "";

            if (data.perfect_matches.length > 0) {
                data.perfect_matches.forEach(name => {
                    const box = document.createElement("div");
                    box.className = "isolated-item-box compact exact-match-box";
                    box.innerHTML = `
                        <div class="item-box-title">${name}</div>
                        <span class="match-badge-100">100% Match</span>
                    `;
                    listPerf.appendChild(box);
                });
            } else {
                listPerf.innerHTML = '<div class="empty-state-notice">No exact 100% matches found.</div>';
            }

            // 2. Similar matches (< 100%) -> Side-by-side comparison boxes
            document.getElementById("count-similar").innerText = data.similar_matches.length;
            const listSim = document.getElementById("list-similar");
            listSim.innerHTML = "";

            if (data.similar_matches.length > 0) {
                if (sectFuzzy) sectFuzzy.style.display = "block";
                data.similar_matches.forEach(item => {
                    const box = document.createElement("div");
                    box.className = "fuzzy-side-by-side-box";
                    box.innerHTML = `
                        <div class="side-col excel-side">
                            <span class="side-label">Excel Name:</span>
                            <span class="side-val-excel">${item.original}</span>
                        </div>
                        <div class="side-arrow">&rarr;</div>
                        <div class="side-col tally-side">
                            <span class="side-label">Tally Ledger:</span>
                            <span class="side-val-tally">${item.matched}</span>
                        </div>
                        <span class="match-badge-fuzzy">${item.score}% Match</span>
                    `;
                    listSim.appendChild(box);
                });
            } else {
                if (sectFuzzy) sectFuzzy.style.display = "none";
            }

            // 3. Non-existing -> Isolated cards with GST & State info
            document.getElementById("count-missing").innerText = data.non_existing.length;
            const missingCardsList = document.getElementById("missing-parties-cards-list");
            const tbody = document.getElementById("tbody-missing");
            missingCardsList.innerHTML = "";
            tbody.innerHTML = "";
            lastNonExistingParties = data.non_existing;

            if (data.non_existing.length > 0) {
                data.non_existing.forEach(item => {
                    const box = document.createElement("div");
                    box.className = "isolated-item-box compact missing";
                    box.innerHTML = `
                        <div class="missing-info-row">
                            <span class="item-box-title">${item.name}</span>
                            <span class="item-sub-tag">State: ${item.state || 'N/A'}</span>
                            <span class="item-sub-tag font-mono">GSTIN: ${item.gstin || 'None'}</span>
                        </div>
                        <span class="missing-badge">${item.gstin ? 'Regular' : 'Unregistered/Consumer'}</span>
                    `;
                    missingCardsList.appendChild(box);
                });
                
                const createBtn = document.getElementById("btn-create-tally-ledgers");
                createBtn.style.display = "inline-flex";
                createBtn.disabled = false;
                createBtn.querySelector("span").innerText = `Create ${data.non_existing.length} Ledgers in Tally`;
            } else {
                missingCardsList.innerHTML = '<div class="empty-state-notice">✓ All party ledgers exist in Tally - No missing ledgers!</div>';
                document.getElementById("btn-create-tally-ledgers").style.display = "none";
            }
            updateStepper(4);
        } else {
            showStatus("mapping-status", null, `❌ Verification failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        document.getElementById("btn-check-parties").disabled = false;
    }
}

async function checkProductNames() {
    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    if (!tempFileId) {
        showStatus("mapping-status", null, "⚠️ Please upload an Excel workbook first.", "error");
        return;
    }
    if (!sheet) {
        showStatus("mapping-status", null, "⚠️ Please select a worksheet sheet first.", "error");
        return;
    }

    const mappings = {};
    let mappingValid = true;

    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        } else if (field.required) {
            mappingValid = false;
        }
    });

    if (!mappingValid) {
        showStatus("mapping-status", null, "⚠️ Please map all required columns before checking.", "error");
        return;
    }

    const stockCo = document.getElementById("tally_stock_company_select").value;
    if (!stockCo) {
        showStatus("mapping-status", null, "⚠️ Please select/sync a Tally Stock Company. This is required for product checking.", "error");
        return;
    }

    showStatus("mapping-status", "check-products-loader", "Checking product names against Tally stock items...", "info");
    document.getElementById("btn-check-products").disabled = true;

    const fromDate = document.getElementById("filter-from-date").value;
    const toDate = document.getElementById("filter-to-date").value;

    try {
        const res = await fetch("/api/check-products", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                stock_company: stockCo,
                from_date: fromDate,
                to_date: toDate,
                header_row: rowVal
            })
        });
        
        const data = await res.json();

        if (data.success) {
            hideStatus("mapping-status");
            switchVerificationView("product-check-results-container");

            // 1. Matched products -> Isolated boxes with 100% Match badge
            document.getElementById("count-products-perfect").innerText = data.perfect_matches.length;
            const listPerf = document.getElementById("list-products-perfect");
            listPerf.innerHTML = "";

            if (data.perfect_matches.length > 0) {
                data.perfect_matches.forEach(item => {
                    const box = document.createElement("div");
                    box.className = "isolated-item-box compact";
                    box.innerHTML = `
                        <div class="item-box-title">${item}</div>
                        <span class="match-badge-100">100% Match</span>
                    `;
                    listPerf.appendChild(box);
                });
            } else {
                listPerf.innerHTML = '<div class="empty-state-notice">No matched stock items found.</div>';
            }

            // 2. Missing products -> Isolated boxes
            document.getElementById("count-products-missing").innerText = data.non_existing.length;
            const listMiss = document.getElementById("list-products-missing");
            listMiss.innerHTML = "";
            lastNonExistingProducts = data.non_existing;
            lastDetectedUnits = data.detected_units || [];

            if (data.non_existing.length > 0) {
                data.non_existing.forEach(item => {
                    const box = document.createElement("div");
                    box.className = "isolated-item-box compact";
                    box.innerHTML = `
                        <div class="item-box-title">${item}</div>
                        <span class="missing-badge">Missing from Stock</span>
                    `;
                    listMiss.appendChild(box);
                });
                
                const createItemsBtn = document.getElementById("btn-create-tally-items");
                createItemsBtn.style.display = "inline-flex";
                createItemsBtn.querySelector("span").innerText = `Create ${data.non_existing.length} Items in Tally`;
            } else {
                listMiss.innerHTML = '<div class="empty-state-notice">✓ All product items exist in Tally Item Stock!</div>';
                document.getElementById("btn-create-tally-items").style.display = "none";
            }
            updateStepper(4);
        } else {
            showStatus("mapping-status", null, `❌ Verification failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        document.getElementById("btn-check-products").disabled = false;
    }
}

async function checkUnits() {
    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    if (!tempFileId) {
        showStatus("mapping-status", null, "⚠️ Please upload an Excel workbook first.", "error");
        return;
    }
    if (!sheet) {
        showStatus("mapping-status", null, "⚠️ Please select a worksheet sheet first.", "error");
        return;
    }

    const mappings = {};
    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        }
    });

    showStatus("mapping-status", "check-units-loader", "Detecting unit types from Excel...", "info");
    document.getElementById("btn-check-units").disabled = true;

    try {
        const res = await fetch("/api/check-units", {
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
        if (data.success) {
            hideStatus("mapping-status");
            switchVerificationView("units-check-results-container");

            const badgeList = document.getElementById("units-badge-list");
            badgeList.innerHTML = "";

            if (data.units && data.units.length > 0) {
                data.units.forEach(u => {
                    const badge = document.createElement("span");
                    badge.className = "unit-pill";
                    badge.innerText = u;
                    badgeList.appendChild(badge);
                });
            } else if (!data.uom_mapped) {
                badgeList.innerHTML = '<span style="font-size: 0.88rem; color: #f87171; font-weight: 700;">⚠️ UOM column is not mapped yet. Please map the UOM column in Step 2.</span>';
            } else {
                badgeList.innerHTML = '<span style="font-size: 0.88rem; color: var(--text-muted); font-style: italic;">No specific unit values found in mapped UOM column — fallback: Nos</span>';
            }
            updateStepper(4);
        } else {
            showStatus("mapping-status", null, `❌ Failed to check units: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        document.getElementById("btn-check-units").disabled = false;
    }
}

async function createTallyLedgers() {
    const ledgerCo = document.getElementById("tally_ledger_company_select").value;
    if (!ledgerCo) {
        alert("Please select a Tally Ledger Company first.");
        return;
    }
    if (!lastNonExistingParties || lastNonExistingParties.length === 0) {
        alert("No non-existing party ledgers to create.");
        return;
    }

    const btn = document.getElementById("btn-create-tally-ledgers");
    btn.disabled = true;
    showStatus("mapping-status", "create-ledgers-loader", `Importing ${lastNonExistingParties.length} missing party ledgers to Tally Prime...`, "info");

    try {
        const res = await fetch("/api/tally/create-missing-ledgers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ledger_company: ledgerCo,
                parties: lastNonExistingParties
            })
        });
        const data = await res.json();

        if (data.success) {
            showStatus("mapping-status", null, `✓ Successfully created ${lastNonExistingParties.length} ledgers in Tally and updated local cache!`, "success");
            btn.style.display = "none";
            lastNonExistingParties = [];
            
            await loadSyncedCompanies();
            document.getElementById("tally_ledger_company_select").value = ledgerCo;
            await loadLedgersForVoucherConfig(ledgerCo);
            
            await checkPartyNames();
        } else {
            showStatus("mapping-status", null, `❌ Failed to create ledgers: ${data.error}`, "error");
            btn.disabled = false;
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
        btn.disabled = false;
    }
}

function openCreateItemsModal() {
    const stockCo = document.getElementById("tally_stock_company_select").value;
    if (!stockCo) {
        alert("Please select a Tally Stock Company first.");
        return;
    }
    if (!lastNonExistingProducts || lastNonExistingProducts.length === 0) {
        alert("No missing products to create.");
        return;
    }

    const list = document.getElementById("missing-items-list-modal");
    list.innerHTML = "";
    lastNonExistingProducts.forEach(item => {
        const li = document.createElement("li");
        li.innerText = `• ${item}`;
        li.style.color = "var(--text-primary)";
        li.style.fontSize = "0.88rem";
        list.appendChild(li);
    });

    const uomDisplay = document.getElementById("detected-units-display");
    const warningBox = document.getElementById("units-warning-box");
    uomDisplay.innerHTML = "";

    if (lastDetectedUnits && lastDetectedUnits.length > 0) {
        lastDetectedUnits.forEach(u => {
            const badge = document.createElement("span");
            badge.innerText = u;
            badge.className = "unit-pill";
            uomDisplay.appendChild(badge);
        });
        warningBox.style.display = "block";
    } else {
        uomDisplay.innerHTML = '<span class="muted-italic">Fallback: Nos (No UOM column mapped)</span>';
        warningBox.style.display = "none";
    }

    document.getElementById("create-stock-items-modal").style.display = "flex";
}

async function submitCreateStockItems() {
    const stockCo = document.getElementById("tally_stock_company_select").value;
    const stockGroup = document.getElementById("new_item_under").value.trim() || "Primary";
    const supplyType = document.getElementById("new_item_supply_type").value || "Goods";

    if (!stockCo) {
        alert("Please select a Tally Stock Company first.");
        return;
    }
    if (!lastNonExistingProducts || lastNonExistingProducts.length === 0) {
        alert("No missing stock items to create.");
        return;
    }

    const createBtn = document.getElementById("btn-create-items-action");
    const openBtn = document.getElementById("btn-create-tally-items");
    const loader = document.getElementById("create-items-loader");
    const btnLoader = document.getElementById("create-items-btn-loader");

    createBtn.disabled = true;
    openBtn.disabled = true;
    loader.style.display = "inline-block";
    if (btnLoader) btnLoader.style.display = "inline-block";

    try {
        const res = await fetch("/api/tally/create-missing-items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: document.getElementById("sheet_select")?.value || "",
                mappings: getSelectedMappings(),
                header_row: parseInt(document.getElementById("header_row")?.value || "1", 10),
                company_name: stockCo,
                under: stockGroup,
                units: document.getElementById("modal-items-detected-units")?.innerText?.trim() || "Nos",
                supply_type: supplyType,
                products: lastNonExistingProducts
            })
        });

        const data = await res.json();
        if (data.success) {
            document.getElementById("create-stock-items-modal").style.display = "none";
            lastNonExistingProducts = [];
            openBtn.style.display = "none";
            await checkProductNames();
            const ignoredText = data.ignored_count ? ` (${data.ignored_count} ignored by Tally)` : "";
            alert(`Successfully created/updated ${data.created_count} Stock Items in Tally!${ignoredText}`);
        } else {
            alert(`Failed to create stock items: ${data.error}`);
        }
    } catch (err) {
        console.error("Error creating stock items:", err);
        alert(`Error creating stock items: ${err.message}`);
    } finally {
        loader.style.display = "none";
        if (btnLoader) btnLoader.style.display = "none";
        createBtn.disabled = false;
        openBtn.disabled = false;
    }
}

// Party & Product Verification and Master Creation Modals

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
    document.getElementById("party-check-results-container").style.display = "none";

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
            document.getElementById("party-check-results-container").style.display = "flex";

            // 1. Perfect matches
            document.getElementById("count-perfect").innerText = data.perfect_matches.length;
            const listPerf = document.getElementById("list-perfect");
            if (data.perfect_matches.length > 0) {
                listPerf.innerText = data.perfect_matches.join(", ");
                document.getElementById("report-perfect").style.display = "block";
            } else {
                listPerf.innerText = "No exact matches found.";
                document.getElementById("report-perfect").style.display = "none";
            }

            // 2. Similar matches
            document.getElementById("count-similar").innerText = data.similar_matches.length;
            const listSim = document.getElementById("list-similar");
            listSim.innerHTML = "";
            if (data.similar_matches.length > 0) {
                data.similar_matches.forEach(item => {
                    const div = document.createElement("div");
                    div.style.display = "flex";
                    div.style.justifyContent = "space-between";
                    div.style.borderBottom = "1px dashed rgba(79, 70, 229, 0.1)";
                    div.style.padding = "4px 0";
                    div.innerHTML = `
                        <span>Original: <strong>${item.original}</strong> &rarr; Tally Match: <strong style="color: var(--accent-primary);">${item.matched}</strong></span>
                        <span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3);">${item.score}% match</span>
                    `;
                    listSim.appendChild(div);
                });
                document.getElementById("report-similar").style.display = "block";
            } else {
                document.getElementById("report-similar").style.display = "none";
            }

            // 3. Non-existing
            document.getElementById("count-missing").innerText = data.non_existing.length;
            const tbody = document.getElementById("tbody-missing");
            tbody.innerHTML = "";
            lastNonExistingParties = data.non_existing;

            if (data.non_existing.length > 0) {
                data.non_existing.forEach(item => {
                    const tr = document.createElement("tr");
                    tr.style.borderBottom = "1px solid var(--border-color)";
                    tr.innerHTML = `
                        <td style="padding: 6px 8px; font-weight: 600;">${item.name}</td>
                        <td style="padding: 6px 8px;">${item.state}</td>
                        <td style="padding: 6px 8px; font-family: monospace;">${item.gstin || '-'}</td>
                        <td style="padding: 6px 8px;">
                            <span class="badge" style="${item.gstin ? 'background: rgba(16, 185, 129, 0.1); color: #10b981; border: 1px solid #10b981;' : 'background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid #f59e0b;'}">
                                ${item.gstin ? 'Regular' : 'Unregistered'}
                            </span>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
                document.getElementById("report-missing").style.display = "block";
                
                const createBtn = document.getElementById("btn-create-tally-ledgers");
                createBtn.style.display = "block";
                createBtn.disabled = false;
                createBtn.querySelector("span").innerText = `Create ${data.non_existing.length} Party Ledgers in Tally`;
            } else {
                document.getElementById("report-missing").style.display = "none";
                document.getElementById("btn-create-tally-ledgers").style.display = "none";
            }
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
    document.getElementById("product-check-results-container").style.display = "none";

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
            document.getElementById("product-check-results-container").style.display = "flex";

            document.getElementById("count-products-perfect").innerText = data.perfect_matches.length;
            const listPerf = document.getElementById("list-products-perfect");
            if (data.perfect_matches.length > 0) {
                listPerf.innerText = data.perfect_matches.join(", ");
                document.getElementById("report-products-perfect").style.display = "block";
            } else {
                listPerf.innerText = "No exact matches found.";
                document.getElementById("report-products-perfect").style.display = "none";
            }

            document.getElementById("count-products-missing").innerText = data.non_existing.length;
            const listMiss = document.getElementById("list-products-missing");
            lastNonExistingProducts = data.non_existing;

            if (data.non_existing.length > 0) {
                listMiss.innerText = data.non_existing.join(", ");
                document.getElementById("report-products-missing").style.display = "block";
                
                const createItemsBtn = document.getElementById("btn-create-tally-items");
                createItemsBtn.style.display = "block";
                createItemsBtn.querySelector("span").innerText = `Create ${data.non_existing.length} Stock Items in Tally`;
            } else {
                listMiss.innerText = "No missing products found.";
                document.getElementById("report-products-missing").style.display = "none";
                document.getElementById("btn-create-tally-items").style.display = "none";
            }
        } else {
            showStatus("mapping-status", null, `❌ Verification failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("mapping-status", null, `❌ Network error: ${err.message}`, "error");
    } finally {
        document.getElementById("btn-check-products").disabled = false;
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

    const listDiv = document.getElementById("missing-items-list-modal");
    listDiv.innerHTML = "";
    lastNonExistingProducts.forEach(prod => {
        const li = document.createElement("li");
        li.style.display = "flex";
        li.style.justifyContent = "space-between";
        li.style.background = "rgba(255, 255, 255, 0.05)";
        li.style.padding = "6px 10px";
        li.style.borderRadius = "4px";
        li.style.fontSize = "0.85rem";
        li.style.color = "var(--text-main)";
        li.innerText = prod;
        listDiv.appendChild(li);
    });

    document.getElementById("create-stock-items-modal").style.display = "block";
}

async function submitCreateStockItems() {
    const stockCo = document.getElementById("tally_stock_company_select").value;
    const sheet = document.getElementById("sheet_select").value;
    const rowVal = document.getElementById("header_row").value || 1;
    const under = document.getElementById("new_item_under").value.trim();
    const units = document.getElementById("new_item_units").value.trim();
    const supplyType = document.getElementById("new_item_supply_type").value;

    const mappings = {};
    targetFields.forEach(field => {
        const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
        if (dropdown && dropdown.value) {
            mappings[field.id] = dropdown.value;
        }
    });

    const loader = document.getElementById("create-items-loader");
    const btnLoader = document.getElementById("create-items-btn-loader");
    const createBtn = document.getElementById("btn-create-items-action");
    const openBtn = document.getElementById("btn-create-tally-items");

    loader.style.display = "inline-block";
    if (btnLoader) btnLoader.style.display = "inline-block";
    createBtn.disabled = true;
    openBtn.disabled = true;

    try {
        const res = await fetch("/api/tally/create-missing-items", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                mappings: mappings,
                header_row: rowVal,
                company_name: stockCo,
                under: under,
                units: units,
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

// Column Header Mapping Grid & Auto-Match Logic

function buildMappingGrid(headers) {
    const grid = document.getElementById("mapping-grid-container");
    grid.innerHTML = "";

    targetFields.forEach(field => {
        const row = document.createElement("div");
        row.className = "mapping-row";
        row.id = `row-${field.id.replace(/\s+/g, "_")}`;

        const labelDiv = document.createElement("div");
        labelDiv.className = "mapping-label";

        const titleSpan = document.createElement("span");
        titleSpan.className = "mapping-title";
        titleSpan.innerText = field.label;

        if (field.required) {
            const reqBadge = document.createElement("span");
            reqBadge.className = "badge";
            reqBadge.innerText = "Required";
            titleSpan.appendChild(reqBadge);
        } else {
            const optBadge = document.createElement("span");
            optBadge.className = "badge badge-optional";
            optBadge.innerText = "Optional";
            titleSpan.appendChild(optBadge);
        }

        const descSpan = document.createElement("span");
        descSpan.className = "mapping-desc";
        descSpan.innerText = field.desc;

        labelDiv.appendChild(titleSpan);
        labelDiv.appendChild(descSpan);

        const autoIndicator = document.createElement("div");
        autoIndicator.className = "auto-mapped-indicator";
        autoIndicator.id = `auto-match-ind-${field.id.replace(/\s+/g, "_")}`;
        autoIndicator.innerHTML = `<span>⚡ Auto-matched</span>`;
        labelDiv.appendChild(autoIndicator);

        const selectContainer = document.createElement("div");
        selectContainer.className = "mapping-select-container";

        const statusIndicator = document.createElement("div");
        statusIndicator.className = "mapping-status";
        statusIndicator.id = `status-dot-${field.id.replace(/\s+/g, "_")}`;

        const wrapper = document.createElement("div");
        wrapper.className = "select-wrapper";

        const select = document.createElement("select");
        select.id = `select-${field.id.replace(/\s+/g, "_")}`;
        select.innerHTML = '<option value="">-- Unmapped --</option>';

        headers.forEach(h => {
            const opt = document.createElement("option");
            opt.value = h;
            opt.innerText = h;
            select.appendChild(opt);
        });

        select.addEventListener("change", (e) => {
            updateMappingRowStatus(field.id, e.target.value);
            if (field.id === "Invoice Date") {
                updateDateSlicerLimits();
            }
            detectAndRenderTaxRates();
        });

        wrapper.appendChild(select);
        selectContainer.appendChild(statusIndicator);
        selectContainer.appendChild(wrapper);

        row.appendChild(labelDiv);
        row.appendChild(selectContainer);
        grid.appendChild(row);
    });
}

function updateMappingRowStatus(fieldId, value) {
    const cleanId = fieldId.replace(/\s+/g, "_");
    const row = document.getElementById(`row-${cleanId}`);
    if (!row) return;
    
    if (value) {
        row.classList.add("mapped");
    } else {
        row.classList.remove("mapped");
    }
}

function triggerAutoMatch() {
    targetFields.forEach(field => {
        const cleanId = field.id.replace(/\s+/g, "_");
        const select = document.getElementById(`select-${cleanId}`);
        const matchTerms = autoMatches[field.id] || [];
        
        let matchedHeader = "";
        for (let h of excelHeaders) {
            const hNorm = h.toLowerCase().trim();
            if (matchTerms.some(term => hNorm === term || hNorm.includes(term))) {
                matchedHeader = h;
                break;
            }
        }

        const autoInd = document.getElementById(`auto-match-ind-${cleanId}`);
        if (matchedHeader) {
            select.value = matchedHeader;
            updateMappingRowStatus(field.id, matchedHeader);
            if (autoInd) autoInd.style.display = "flex";
            if (field.id === "Invoice Date") {
                updateDateSlicerLimits();
            }
        } else {
            if (autoInd) autoInd.style.display = "none";
        }
    });
    
    detectAndRenderTaxRates();
}

async function updateDateSlicerLimits() {
    const sheet = document.getElementById("sheet_select").value;
    const dateSelect = document.getElementById("select-Invoice_Date");
    if (!dateSelect) return;
    const dateCol = dateSelect.value;
    const rowVal = document.getElementById("header_row").value || 1;
    const container = document.getElementById("date-slicer-container");
    const fromInput = document.getElementById("filter-from-date");
    const toInput = document.getElementById("filter-to-date");

    if (!tempFileId || !sheet || !dateCol) {
        if (container) container.style.display = "none";
        return;
    }

    try {
        const res = await fetch("/api/get-date-range", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                file_id: tempFileId,
                sheet_name: sheet,
                date_col: dateCol,
                header_row: rowVal
            })
        });
        const data = await res.json();
        
        if (data.success && data.min_date && data.max_date) {
            fromInput.value = data.min_date;
            toInput.value = data.max_date;
            fromInput.min = data.min_date;
            fromInput.max = data.max_date;
            toInput.min = data.min_date;
            toInput.max = data.max_date;
            if (container) container.style.display = "block";
        } else {
            if (container) container.style.display = "none";
        }
    } catch (err) {
        console.error("Failed to fetch date range limits:", err);
        if (container) container.style.display = "none";
    }
}

// UI Utility Helpers (Status boxes & Loaders)

function showStatus(elemId, loaderId, message, type) {
    const statusDiv = document.getElementById(elemId);
    if (!statusDiv) return;
    
    statusDiv.style.display = "block";
    statusDiv.className = `status-box status-${type}`;
    statusDiv.innerHTML = "";
    
    if (loaderId) {
        const loader = document.createElement("div");
        loader.className = "loader";
        loader.style.display = "inline-block";
        loader.style.marginRight = "10px";
        loader.style.verticalAlign = "middle";
        statusDiv.appendChild(loader);
    }
    
    const txt = document.createElement("span");
    txt.innerText = message;
    txt.style.verticalAlign = "middle";
    statusDiv.appendChild(txt);
}

function hideStatus(elemId) {
    const statusDiv = document.getElementById(elemId);
    if (statusDiv) {
        statusDiv.style.display = "none";
    }
}

function updateStepper(activeStep) {
    for (let i = 1; i <= 5; i++) {
        const node = document.getElementById(`step-node-${i}`);
        const line = document.getElementById(`step-line-${i}`);
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

function scrollToStep(cardId) {
    const el = document.getElementById(cardId);
    if (el) {
        if (el.style.display === "none") {
            el.style.display = "block";
        }
        const yOffset = -90; // account for sticky header
        const y = el.getBoundingClientRect().top + window.pageYOffset + yOffset;
        window.scrollTo({ top: y, behavior: "smooth" });
    }
}

function getSelectedMappings() {
    const mappings = {};
    if (typeof targetFields !== "undefined" && Array.isArray(targetFields)) {
        targetFields.forEach(field => {
            const dropdown = document.getElementById(`select-${field.id.replace(/\s+/g, "_")}`);
            if (dropdown && dropdown.value) {
                mappings[field.id] = dropdown.value;
            }
        });
    }
    return mappings;
}

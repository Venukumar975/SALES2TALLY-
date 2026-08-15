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

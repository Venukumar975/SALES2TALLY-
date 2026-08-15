// Excel File Upload & Sheet Handling

function handleFileSelected() {
    const excelInput = document.getElementById("excel_file");
    const file = excelInput.files[0];
    if (!file) return;

    originalFilename = file.name;
    document.getElementById("uploaded-filename").innerText = originalFilename;
    document.getElementById("dropzone").style.display = "none";
    document.getElementById("file-info-container").style.display = "flex";

    uploadFile(file);
}

function resetFile() {
    const excelInput = document.getElementById("excel_file");
    excelInput.value = "";
    tempFileId = "";
    originalFilename = "";
    document.getElementById("dropzone").style.display = "flex";
    document.getElementById("file-info-container").style.display = "none";
    document.getElementById("sheet-select-container").style.display = "none";
    document.getElementById("card-mapping").style.display = "none";
    document.getElementById("card-tally").style.display = "none";
    document.getElementById("card-generate").style.display = "none";
    document.getElementById("success-container").style.display = "none";
    document.getElementById("excel-success-container").style.display = "none";
    document.getElementById("sheet_select").innerHTML = '<option value="">-- Choose a sheet --</option>';
    hideStatus("upload-status");
    hideStatus("sheet-status");
    hideStatus("mapping-status");
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append("excel_file", file);

    showStatus("upload-status", "upload-loader", "Uploading and parsing workbook...", "info");

    try {
        const res = await fetch("/upload", {
            method: "POST",
            body: formData
        });
        const data = await res.json();

        if (data.success) {
            tempFileId = data.file_id;
            
            const sheetSelect = document.getElementById("sheet_select");
            sheetSelect.innerHTML = '<option value="">-- Choose a sheet --</option>';
            data.sheets.forEach(s => {
                const opt = document.createElement("option");
                opt.value = s;
                opt.innerText = s;
                sheetSelect.appendChild(opt);
            });

            document.getElementById("sheet-select-container").style.display = "block";
            showStatus("upload-status", null, `✓ File uploaded successfully. Found ${data.sheets.length} worksheets.`, "success");

            if (data.sheets.length > 0) {
                sheetSelect.value = data.sheets[0];
                analyzeSheet(data.sheets[0]);
            }
        } else {
            showStatus("upload-status", null, `❌ Upload failed: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("upload-status", null, `❌ Network error: ${err.message}`, "error");
    }
}

async function analyzeSheet(sheet) {
    const rowVal = document.getElementById("header_row").value || 1;
    showStatus("sheet-status", "sheet-loader", `Analyzing sheet headers (Row ${rowVal})...`, "info");
    
    document.getElementById("card-mapping").style.display = "none";
    document.getElementById("card-tally").style.display = "none";
    document.getElementById("card-generate").style.display = "none";

    try {
        const res = await fetch("/get-headers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_id: tempFileId, sheet_name: sheet, header_row: rowVal })
        });
        const data = await res.json();

        if (data.success) {
            excelHeaders = data.headers;
            buildMappingGrid(data.headers);
            triggerAutoMatch();
            hideStatus("sheet-status");
            
            document.getElementById("card-mapping").style.display = "block";
            document.getElementById("card-tally").style.display = "block";
            document.getElementById("card-generate").style.display = "block";
        } else {
            showStatus("sheet-status", null, `❌ Failed to read headers: ${data.error}`, "error");
        }
    } catch (err) {
        showStatus("sheet-status", null, `❌ Network error: ${err.message}`, "error");
    }
}

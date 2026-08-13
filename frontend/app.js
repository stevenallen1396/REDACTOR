const batchFiles = new Map(); // relativePath -> File
const ALLOWED_EXTENSIONS = ["pdf", "eml", "msg"];

function fileKey(file) {
  return file.webkitRelativePath || file.relativePath || file.name;
}

function addFilesToMap(map, files, extFilter) {
  for (const f of files) {
    const ext = f.name.split(".").pop().toLowerCase();
    if (!extFilter.includes(ext)) continue;
    let key = fileKey(f);
    if (map.has(key)) {
      let n = 2;
      while (map.has(`${key} (${n})`)) n++;
      key = `${key} (${n})`;
    }
    map.set(key, f);
  }
}

// Recursively walk a dropped folder (or file) using the WebKit DataTransferItem
// entry API so "drag a folder in" works, not just individual files.
function readDirectoryEntries(reader) {
  return new Promise((resolve, reject) => {
    const all = [];
    function readBatch() {
      reader.readEntries((entries) => {
        if (entries.length === 0) {
          resolve(all);
          return;
        }
        all.push(...entries);
        readBatch();
      }, reject);
    }
    readBatch();
  });
}

function fileFromEntry(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function collectFilesFromEntry(entry, basePath, out) {
  if (entry.isFile) {
    const file = await fileFromEntry(entry);
    const relativePath = (basePath ? basePath + "/" : "") + entry.name;
    try {
      Object.defineProperty(file, "relativePath", { value: relativePath });
    } catch {
      // ignore if it can't be set; fileKey() falls back to file.name
    }
    out.push(file);
  } else if (entry.isDirectory) {
    const reader = entry.createReader();
    const entries = await readDirectoryEntries(reader);
    const nextBase = (basePath ? basePath + "/" : "") + entry.name;
    for (const child of entries) {
      await collectFilesFromEntry(child, nextBase, out);
    }
  }
}

async function filesFromDataTransfer(dataTransfer) {
  const items = dataTransfer.items;
  if (!items || !items.length || !items[0].webkitGetAsEntry) {
    return Array.from(dataTransfer.files || []);
  }
  const entries = Array.from(items)
    .map((item) => item.webkitGetAsEntry())
    .filter(Boolean);
  if (entries.length === 0) return Array.from(dataTransfer.files || []);

  const out = [];
  for (const entry of entries) {
    await collectFilesFromEntry(entry, "", out);
  }
  return out;
}

function setupDropzone(dropzoneEl, onFiles) {
  ["dragenter", "dragover"].forEach((evt) =>
    dropzoneEl.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzoneEl.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    dropzoneEl.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzoneEl.classList.remove("dragover");
    })
  );
  dropzoneEl.addEventListener("drop", async (e) => {
    const files = await filesFromDataTransfer(e.dataTransfer);
    onFiles(files);
  });
}

function setupBrowseButton(buttonEl, inputEl, onFiles) {
  buttonEl.addEventListener("click", (e) => {
    e.stopPropagation();
    inputEl.click();
  });
  inputEl.addEventListener("change", () => {
    onFiles(Array.from(inputEl.files));
    inputEl.value = "";
  });
}

function renderFileList(listEl, filesMap, onRemove) {
  listEl.innerHTML = "";
  for (const key of filesMap.keys()) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = key;
    const removeBtn = document.createElement("button");
    removeBtn.textContent = "remove";
    removeBtn.className = "remove";
    removeBtn.addEventListener("click", () => {
      filesMap.delete(key);
      onRemove();
    });
    li.append(label, removeBtn);
    listEl.appendChild(li);
  }
}

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ---- Batch panel ----

const batchDropzone = document.getElementById("batch-dropzone");
const batchInput = document.getElementById("batch-input");
const batchFolderInput = document.getElementById("batch-folder-input");
const batchFileList = document.getElementById("batch-file-list");
const exemptionsEl = document.getElementById("exemptions");
const mustRedactEl = document.getElementById("must-redact");
const processBtn = document.getElementById("process-btn");
const clearBtn = document.getElementById("clear-btn");
const batchStatus = document.getElementById("batch-status");

function refreshBatchUI() {
  renderFileList(batchFileList, batchFiles, refreshBatchUI);
  processBtn.disabled = batchFiles.size === 0;
}

function addBatchFiles(files) {
  const before = batchFiles.size;
  addFilesToMap(batchFiles, files, ALLOWED_EXTENSIONS);
  const skipped = files.length - (batchFiles.size - before);
  refreshBatchUI();
  if (skipped > 0) {
    setStatus(batchStatus, `Ignored ${skipped} file(s) that weren't .pdf, .eml, or .msg.`);
  }
}

setupDropzone(batchDropzone, addBatchFiles);
setupBrowseButton(document.getElementById("batch-browse-files"), batchInput, addBatchFiles);
setupBrowseButton(document.getElementById("batch-browse-folder"), batchFolderInput, addBatchFiles);

clearBtn.addEventListener("click", () => {
  batchFiles.clear();
  refreshBatchUI();
  setStatus(batchStatus, "");
});

processBtn.addEventListener("click", async () => {
  if (batchFiles.size === 0) return;
  processBtn.disabled = true;
  setStatus(batchStatus, `Processing ${batchFiles.size} file(s)... emails are converted to PDF first, then everything is redacted.`);

  const form = new FormData();
  for (const [key, f] of batchFiles.entries()) form.append("files", f, key);
  form.append("exemptions", exemptionsEl.value);
  form.append("must_redact", mustRedactEl.value);

  try {
    const res = await fetch("/api/process", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Processing failed");
    }
    const zipBlob = await res.blob();
    downloadBlob(zipBlob, "redacted.zip");
    setStatus(batchStatus, `Done. Downloaded redacted.zip (${batchFiles.size} file(s)).`, "success");
  } catch (e) {
    setStatus(batchStatus, `Error: ${e.message}`, "error");
  } finally {
    processBtn.disabled = batchFiles.size === 0;
  }
});

refreshBatchUI();

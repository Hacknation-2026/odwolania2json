// GUI entry point: state, processing queue and page events.
import { extract, fetchClasses } from "./api.js";
import { fromDrop, fromFolderPicker } from "./folders.js";
import { classChips, errorCard, markProcessing, queuedCard, resultCard } from "./render.js";
import { isPdf, jsonPath, saveFile, toText } from "./util.js";
import { zip } from "./zip.js";

const MAX_PARALLEL = 2; // OCR is CPU-heavy: process at most two files at a time

const $ = (id) => document.getElementById(id);
const list = $("list");

const results = []; // {path, data} - path of the .json inside output.zip, e.g. "przyklad_01/odwolanie.json"
const queue = [];
const usedPaths = new Set(); // the same path twice -> "odwolanie (2).pdf", nothing is overwritten in the ZIP
const pdfUrls = []; // object URLs of PDF previews, released on "Wyczyść"
let pending = 0, running = 0;
let labels = {}; // class name -> display label

function updateToolbar() {
  $("toolbar").classList.toggle("show", list.children.length > 0);
  $("summary").textContent = pending ? `Przetwarzanie… (${pending} w kolejce)` : `Gotowe: ${results.length} plik(ów)`;
  $("all").disabled = pending > 0 || results.length === 0;
}

function uniquePath(path) {
  let candidate = path;
  for (let n = 2; usedPaths.has(candidate.toLowerCase()); n++) candidate = path.replace(/(\.pdf)?$/i, ` (${n})$1`);
  usedPaths.add(candidate.toLowerCase());
  return candidate;
}

/** Shows a card at once; processing waits in the queue. */
function enqueue(file, path = file.name) {
  path = uniquePath(path);
  const el = queuedCard(path, file);
  list.append(el);
  pending++;
  updateToolbar();
  queue.push({ file, path, el });
  pump();
}

function pump() {
  while (running < MAX_PARALLEL && queue.length) {
    const job = queue.shift();
    running++;
    process(job).finally(() => { running--; pump(); });
  }
}

async function process({ file, path, el }) {
  markProcessing(el, file);
  try {
    const result = await extract(file);
    results.push({ path: jsonPath(path), data: result.data });
    resultCard(el, { path, file, result, label: labels[result.document_type] || result.document_type }, {
      onDownload: () => saveFile(jsonPath(file.name), new Blob([toText(result.data)], { type: "application/json" })),
      onCopy: () => navigator.clipboard.writeText(toText(result.data)),
      pdfUrl: () => { const url = URL.createObjectURL(file); pdfUrls.push(url); return url; },
    });
  } catch (err) {
    errorCard(el, path, err.message);
    results.push({ path: jsonPath(path), data: null }); // like the CLI: empty file
  } finally {
    pending--;
    updateToolbar();
  }
}

const addFiles = (files) => [...files].filter((f) => isPdf(f.name)).forEach((f) => enqueue(f));

function addFolder(files) {
  const found = fromFolderPicker(files);
  if (!found.length) return alert("W wybranym folderze (ani w jego podfolderach) nie ma plików PDF.");
  found.forEach(({ file, path }) => enqueue(file, path));
}

// ---- events
const drop = $("drop"), input = $("input"), folderInput = $("folderInput"), pickFolder = $("pickFolder");

input.onchange = () => { addFiles(input.files); input.value = ""; };
folderInput.onchange = () => { addFolder(folderInput.files); folderInput.value = ""; };
const openFolder = (e) => { e.preventDefault(); e.stopPropagation(); folderInput.click(); };
pickFolder.addEventListener("click", openFolder);
pickFolder.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") openFolder(e); });

["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", async (e) => {
  const files = e.dataTransfer.files;
  const found = await fromDrop(e.dataTransfer);
  if (found === null) return addFiles(files);
  found.forEach(({ file, path }) => enqueue(file, path));
});

$("all").onclick = () =>
  saveFile("output.zip", zip(results.map((r) => ({ path: r.path, text: toText(r.data) }))));

$("clear").onclick = () => {
  if (pending) return;
  list.innerHTML = "";
  results.length = 0;
  usedPaths.clear();
  pdfUrls.splice(0).forEach((url) => URL.revokeObjectURL(url));
  updateToolbar();
};

// supported classes come from the YAML config, so new classes show up automatically
fetchClasses()
  .then((classes) => {
    labels = Object.fromEntries(Object.values(classes).map((c) => [c.name, c.label || c.name]));
    classChips($("classes"), classes);
  })
  .catch(() => { /* the list is optional - upload still works without it */ });

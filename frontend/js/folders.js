// Folders, like the CLI: PDFs in the folder and in its direct subfolders (one level deep).
// Paths keep the folder's name ("przyklad_01/odwolanie.pdf"), so several case folders uploaded
// one after another stay apart in output.zip instead of repeating "odwolanie.json".
import { isPdf } from "./util.js";

/** Files from <input webkitdirectory> -> [{file, path}] ("chosen/case1/x.pdf" is kept, deeper is skipped). */
export function fromFolderPicker(files) {
  return [...files]
    .map((file) => ({ file, parts: (file.webkitRelativePath || file.name).split("/") }))
    .filter(({ file, parts }) => isPdf(file.name) && parts.length >= 2 && parts.length <= 3)
    .map(({ file, parts }) => ({ file, path: parts.join("/") }))
    .sort((a, b) => a.path.localeCompare(b.path));
}

const readAll = (dir) =>
  new Promise((resolve) => {
    const reader = dir.createReader(), all = [];
    const next = () =>
      reader.readEntries((batch) => (batch.length ? (all.push(...batch), next()) : resolve(all)), () => resolve(all));
    next();
  });

const entryFile = (entry) => new Promise((resolve) => entry.file(resolve, () => resolve(null)));

async function collect(entry, prefix, depth) {
  if (entry.isFile) {
    if (!isPdf(entry.name)) return [];
    const file = await entryFile(entry);
    return file ? [{ file, path: prefix + entry.name }] : [];
  }
  if (depth > 1) return []; // deeper than one level below the dropped folder
  const children = (await readAll(entry)).sort((a, b) => a.name.localeCompare(b.name));
  const found = [];
  for (const child of children) found.push(...(await collect(child, prefix + entry.name + "/", depth + 1)));
  return found;
}

/** Drag & drop -> [{file, path}]; null when nothing but plain files was dropped. */
export async function fromDrop(dataTransfer) {
  const entries = [...dataTransfer.items].map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.some((entry) => entry.isDirectory)) return null;
  const found = [];
  for (const entry of entries) found.push(...(await collect(entry, "", 0)));
  return found;
}

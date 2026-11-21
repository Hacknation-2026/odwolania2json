// Small helpers shared by the GUI modules.

/** Escapes text before it goes into innerHTML (document content must never become markup). */
export const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

export const kb = (n) => (n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1e3)) + " KB");

export const isPdf = (name) => /\.pdf$/i.test(name);

/** "case1/odwolanie.pdf" -> "case1/odwolanie.json" */
export const jsonPath = (pdfPath) => pdfPath.replace(/\.pdf$/i, "") + ".json";

/** JSON text of a result; a document outside the classes -> empty file (UZP requirement). */
export const toText = (obj) => (obj == null ? "" : JSON.stringify(obj, null, 2));

/** Lets the browser save a Blob under the given file name. */
export function saveFile(name, blob) {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

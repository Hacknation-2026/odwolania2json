// Backend API (backend/app/main.py). Everything runs locally; the server keeps no files.

/** Document classes from the YAML config: {name: {name, label, description}}. */
export async function fetchClasses() {
  const res = await fetch("/api/classes");
  if (!res.ok) throw new Error(`Błąd ${res.status}`);
  return res.json();
}

/** Classifies one PDF and extracts its fields: {document_type, data, trace}. */
export async function extract(file) {
  const form = new FormData();
  form.append("files", file);
  const res = await fetch("/api/extract", { method: "POST", body: form });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail || `Błąd ${res.status}`);
  return body[0];
}

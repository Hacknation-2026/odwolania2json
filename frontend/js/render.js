// Result cards: badge + path + icon buttons; panels for PDF/JSON comparison and the processing trace.
import { esc, kb, toText } from "./util.js";

// line icons (stroke = currentColor: they follow the text colour / the red download button)
const svg = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
export const ICONS = {
  compare: svg('<rect x="3" y="4" width="7" height="16" rx="1.5"/><rect x="14" y="4" width="7" height="16" rx="1.5"/>'),
  trace: svg('<path d="M4 6h16M4 12h10M4 18h7"/><circle cx="18" cy="16" r="3"/><path d="m20.2 18.2 1.8 1.8"/>'),
  copy: svg('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'),
  check: svg('<path d="m5 12 5 5 9-10"/>'),
  download: svg('<path d="M12 4v11m0 0-4-4m4 4 4-4M5 19h14"/>'),
};

/** JSON with coloured keys / values (escaped first, so document text cannot inject HTML). */
const highlight = (obj) =>
  esc(toText(obj)).replace(
    /(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(-?\d+(?:\.\d+)?)\b|\bnull\b/g,
    (m, str, colon, num) =>
      str ? `<span class="${colon ? "j-key" : "j-str"}">${str}</span>${colon || ""}`
        : num ? `<span class="j-num">${num}</span>` : `<span class="j-null">null</span>`,
  );

const iconButton = (act, title, icon, extra = "") =>
  `<button class="icon ${extra}" data-act="${act}" title="${title}" aria-label="${title}">${icon}</button>`;

/** Card of a file waiting in the queue. */
export function queuedCard(path, file) {
  const el = document.createElement("div");
  el.className = "item";
  el.innerHTML = `<div class="row">
      <div class="spinner"></div>
      <div class="name"><b>${esc(path)}</b><small>${kb(file.size)} · w kolejce…</small></div>
    </div>`;
  return el;
}

export const markProcessing = (el, file) => (el.querySelector("small").textContent = `${kb(file.size)} · przetwarzanie…`);

export function errorCard(el, path, message) {
  el.innerHTML = `<div class="row">
      <span class="badge err">błąd</span>
      <div class="name"><b>${esc(path)}</b><small>${esc(message)}</small></div>
    </div>`;
}

/**
 * Fills a card with a result. handlers: {onDownload(), onCopy(), pdfUrl()} - pdfUrl() is called
 * the first time the comparison opens (preview of the uploaded file, nothing stored on the server).
 */
export function resultCard(el, { path, file, result, label }, handlers) {
  const { data, trace = {} } = result;
  const known = data != null;
  const cls = trace.classification || {};
  const conf = cls.confidence != null ? ` · ${Math.round(cls.confidence * 100)}%` : "";
  const ocr = (trace.pages || []).filter((p) => p.source === "ocr").length;
  const details = `${kb(file.size)} · ${trace.pages?.length ?? 0} str.${ocr ? ` (OCR: ${ocr})` : ""}${trace.seconds ? ` · ${trace.seconds}s` : ""}`;

  el.innerHTML = `<div class="row">
      <span class="badge ${known ? "ok" : "err"}">${esc(known ? label : "nie rozpoznano")}${conf}</span>
      <div class="name"><b title="${esc(path)}">${esc(path)}</b><small>${details}</small></div>
      <div class="actions">
        ${iconButton("compare", "Porównaj PDF i JSON", ICONS.compare)}
        ${iconButton("trace", "Ślad przetwarzania", ICONS.trace)}
        ${iconButton("copy", "Kopiuj JSON", ICONS.copy)}
        ${iconButton("dl", "Pobierz JSON", ICONS.download, "primary")}
      </div>
    </div>
    <div class="panel" data-panel="compare" hidden>
      <div class="compare">
        <div><h3>Dokument PDF</h3><iframe title="Podgląd PDF: ${esc(file.name)}"></iframe></div>
        <div><h3>Wynik JSON</h3>${known ? `<pre>${highlight(data)}</pre>`
          : `<div class="empty">Pusty plik JSON – dokument spoza obsługiwanych klas.</div>`}</div>
      </div>
    </div>
    <div class="panel" data-panel="trace" hidden><pre>${esc(JSON.stringify(trace, null, 2))}</pre></div>`;

  for (const name of ["compare", "trace"]) { // icon buttons toggle the panels below the row
    const button = el.querySelector(`[data-act="${name}"]`);
    const panel = el.querySelector(`[data-panel="${name}"]`);
    button.setAttribute("aria-expanded", "false");
    button.onclick = () => {
      panel.hidden = !panel.hidden;
      button.classList.toggle("on", !panel.hidden);
      button.setAttribute("aria-expanded", String(!panel.hidden));
      const frame = panel.querySelector("iframe");
      if (frame && !panel.hidden && !frame.src) frame.src = handlers.pdfUrl();
    };
  }
  el.querySelector('[data-act="dl"]').onclick = handlers.onDownload;
  el.querySelector('[data-act="copy"]').onclick = async (e) => {
    const button = e.currentTarget;
    await handlers.onCopy();
    button.innerHTML = ICONS.check;
    button.title = "Skopiowano";
    setTimeout(() => { button.innerHTML = ICONS.copy; button.title = "Kopiuj JSON"; }, 1500);
  };
}

/** Chips with supported document classes (they come from the YAML config). */
export function classChips(box, classes) {
  box.innerHTML = "<span>Obsługiwane dokumenty:</span>" +
    Object.values(classes)
      .map((c) => `<span class="chip" title="${esc(c.description.trim())}">${esc(c.label || c.name)}</span>`)
      .join("") +
    `<span class="note">Inne dokumenty nie są klasyfikowane – dostają pusty plik JSON.</span>`;
  box.hidden = false;
}

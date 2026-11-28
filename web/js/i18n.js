// Lightweight runtime i18n. English remains the canonical source language; French uses a
// lazily loaded exact/phrase dictionary and falls back to English for new or untranslated strings.
const param = new URLSearchParams(location.search).get("lang");
const stored = localStorage.getItem("franceciv.lang");
export const lang = param === "fr" || (!param && stored === "fr") ? "fr" : "en";
if (param === "fr" || param === "en") localStorage.setItem("franceciv.lang", lang);

let phrases = null;
let normalizedPhrases = null;
let observer = null;
let translating = false;

export async function initI18n() {
  document.documentElement.lang = lang;
  if (lang !== "fr") return;
  try {
    const r = await fetch("data/i18n_fr.json");
    phrases = r.ok ? await r.json() : {};
    normalizedPhrases = Object.fromEntries(Object.entries(phrases).map(([source, target]) => [normalizeText(source), target]));
  } catch {
    phrases = {};
  }
  translateTree(document.body);
  observer = new MutationObserver((mutations) => {
    if (translating) return;
    for (const m of mutations) {
      for (const node of m.addedNodes) translateTree(node);
      if (m.type === "attributes" && m.target) translateTree(m.target);
    }
  });
  observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["placeholder", "title", "aria-label"] });
}

function normalizeText(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

export function tr(text) {
  if (lang !== "fr" || !text || !phrases) return text;
  const exact = phrases[text];
  if (exact) return exact;
  return normalizedPhrases?.[normalizeText(text)] || text;
}

function translateText(node) {
  const old = node.nodeValue;
  if (!old || !old.trim()) return;
  const next = tr(old);
  if (next !== old) {
    translating = true;
    node.nodeValue = next;
    translating = false;
  }
}

const SKIP = new Set(["SCRIPT", "STYLE", "CODE", "CANVAS"]);
function translateTree(root) {
  if (lang !== "fr" || !phrases || !root) return;
  if (root.nodeType === Node.TEXT_NODE) return translateText(root);
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return;
  if (root.nodeType === Node.ELEMENT_NODE && SKIP.has(root.tagName)) return;
  translating = true;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      return p && !SKIP.has(p.tagName) && n.nodeValue.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const n of nodes) {
    const old = n.nodeValue, next = tr(old);
    if (next !== old) n.nodeValue = next;
  }
  const elements = root.nodeType === Node.ELEMENT_NODE ? [root, ...root.querySelectorAll("[placeholder],[title],[aria-label]")] : [...root.querySelectorAll("[placeholder],[title],[aria-label]")];
  for (const el of elements) {
    for (const attr of ["placeholder", "title", "aria-label"]) {
      const old = el.getAttribute(attr);
      if (!old) continue;
      const next = tr(old);
      if (next !== old) el.setAttribute(attr, next);
    }
  }
  if (document.title) document.title = tr(document.title);
  translating = false;
}

export function installLanguageSwitch() {
  const box = document.querySelector(".tb-buttons");
  if (!box || document.getElementById("lang-switch")) return;
  const wrap = document.createElement("div");
  wrap.id = "lang-switch";
  wrap.setAttribute("role", "group");
  wrap.setAttribute("aria-label", "Language");
  for (const code of ["en", "fr"]) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn lang-btn";
    b.textContent = code.toUpperCase();
    b.setAttribute("aria-pressed", String(code === lang));
    b.setAttribute("aria-label", code === "en" ? "English" : "Français");
    b.addEventListener("click", () => {
      if (code === lang) return;
      localStorage.setItem("franceciv.lang", code);
      const u = new URL(location.href);
      u.searchParams.set("lang", code);
      location.href = u;
    });
    wrap.appendChild(b);
  }
  box.prepend(wrap);
}

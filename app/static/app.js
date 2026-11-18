// Degbot chat page: plain JavaScript, no framework, no build step.
// Model output is only ever inserted as text nodes (never innerHTML).
"use strict";

const MAX_CHARS = 500;
const chat = document.getElementById("chat");
const form = document.getElementById("composer");
const input = document.getElementById("question");
const sendButton = document.getElementById("send");
const counter = document.getElementById("counter");
const welcome = document.getElementById("welcome");
const exampleButtons = [...document.querySelectorAll(".example")];
const sourcesDialog = document.getElementById("sources-dialog");

let busy = false;
let messageCount = 0;

// ------------------------------------------------------------------ helpers

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function scrollToBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function setBusy(value) {
  busy = value;
  sendButton.disabled = value || input.value.trim() === "";
  exampleButtons.forEach((b) => (b.disabled = value));
}

async function postJSON(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data = null;
  try {
    data = await response.json();
  } catch {
    /* non-JSON response */
  }
  if (!response.ok) {
    const message = data?.error?.message || `The server answered with status ${response.status}.`;
    throw new Error(message);
  }
  return data;
}

// --------------------------------------------- answer text -> safe DOM nodes

const CITATION_OR_BOLD = /\*\*([^*]+)\*\*|\[(\d+(?:\s*[,;–-]\s*\d+)*)\]/g;
const LIST_ITEM = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/;

function expandNumbers(group) {
  const numbers = [];
  for (const part of group.split(/[,;]/)) {
    const [a, b] = part.split(/[–-]/).map((x) => parseInt(x, 10));
    if (Number.isNaN(a)) continue;
    const end = Number.isNaN(b) || b === undefined ? a : b;
    for (let n = a; n <= end && n - a < 20; n++) numbers.push(n);
  }
  return numbers;
}

function appendInline(parent, text, msgId, citedNumbers, sourceIndex) {
  let last = 0;
  for (const match of text.matchAll(CITATION_OR_BOLD)) {
    parent.append(text.slice(last, match.index));
    if (match[1] !== undefined) {
      parent.append(el("strong", null, match[1]));
    } else {
      for (const n of expandNumbers(match[2])) {
        if (citedNumbers.has(n)) {
          const link = el("a", "cite", String(n));
          link.href = `#src-${msgId}-${sourceIndex.get(n) ?? 0}`;
          link.setAttribute("aria-label", `Source ${n}`);
          link.addEventListener("click", (event) => {
            event.preventDefault();
            highlightSource(msgId, n);
          });
          parent.append(link);
        } else {
          parent.append(`[${n}]`);
        }
      }
    }
    last = match.index + match[0].length;
  }
  parent.append(text.slice(last));
}

function renderAnswerText(text, msgId, citedNumbers, sourceIndex) {
  const container = el("div", "answer");
  let list = null;
  let paragraph = null;
  for (const line of text.split(/\r?\n/)) {
    const item = line.match(LIST_ITEM);
    if (item) {
      paragraph = null;
      if (!list) {
        list = el(/^\s*\d/.test(line) ? "ol" : "ul");
        container.append(list);
      }
      const li = el("li");
      appendInline(li, item[1], msgId, citedNumbers, sourceIndex);
      list.append(li);
    } else if (line.trim() === "") {
      list = null;
      paragraph = null;
    } else {
      list = null;
      if (paragraph) paragraph.append(el("br"));
      else {
        paragraph = el("p");
        container.append(paragraph);
      }
      appendInline(paragraph, line, msgId, citedNumbers, sourceIndex);
    }
  }
  return container;
}

function highlightSource(msgId, n) {
  const card = document.querySelector(`[data-source-of~="${msgId}-${n}"]`);
  if (!card) return;
  card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  card.classList.add("highlight");
  setTimeout(() => card.classList.remove("highlight"), 1600);
}

// ------------------------------------------------------------------ messages

function addUserMessage(text) {
  chat.append(el("div", "msg msg-user", text));
}

function addLoading() {
  const box = el("div", "msg msg-bot");
  const row = el("div", "loading");
  const label = el("span", null, "Searching the sources…");
  row.append(el("span", "spinner"), label);
  box.append(row);
  chat.append(box);
  const started = Date.now();
  const timer = setInterval(() => {
    const seconds = Math.round((Date.now() - started) / 1000);
    label.textContent =
      seconds < 4
        ? "Searching the sources…"
        : `Searching the sources… ${seconds} s (this usually takes about 10 s)`;
  }, 1000);
  return { box, stop: () => clearInterval(timer) };
}

// One card per cited document, listing all its citation numbers, e.g. "[1][3]".
function sourceCard(source, msgId, index) {
  const card = el("article", "source-card");
  card.id = `src-${msgId}-${index}`;
  card.dataset.sourceOf = source.numbers.map((n) => `${msgId}-${n}`).join(" ");
  const head = el("div", "source-head");
  head.append(el("span", "source-num", source.numbers.map((n) => `[${n}]`).join("")));
  head.append(el("span", "lang-tag", (source.language || "?").toUpperCase()));
  card.append(head);
  card.append(el("div", "source-title", source.title));
  const link = el("a", "source-link", new URL(source.url).hostname.replace(/^www\./, ""));
  link.href = source.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.title = source.url;
  card.append(link);
  return card;
}

function feedbackButtons(questionId) {
  const wrap = el("div", "feedback");
  const status = el("span", "feedback-status");
  const up = el("button", "icon-button", "👍");
  const down = el("button", "icon-button", "👎");
  up.type = down.type = "button";
  up.setAttribute("aria-label", "Helpful");
  down.setAttribute("aria-label", "Not helpful");
  up.setAttribute("aria-pressed", "false");
  down.setAttribute("aria-pressed", "false");

  async function send(helpful, button) {
    up.disabled = down.disabled = true;
    try {
      await postJSON("/api/feedback", { question_id: questionId, helpful });
      button.setAttribute("aria-pressed", "true");
      status.textContent = "Thanks for your feedback!";
    } catch (error) {
      up.disabled = down.disabled = false;
      status.textContent = error.message;
    }
  }
  up.addEventListener("click", () => send(true, up));
  down.addEventListener("click", () => send(false, down));
  wrap.append(status, up, down);
  return wrap;
}

function renderAnswer(box, result) {
  box.replaceChildren();
  const msgId = ++messageCount;
  box.lang = result.language === "de" ? "de" : "en";

  if (result.refused) {
    const text =
      result.language === "de"
        ? "Keine Antwort in den Quellen gefunden"
        : "No answer found in the sources";
    const banner = el("div", "refusal-banner");
    banner.append(el("span", null, "⚠"), el("span", null, text));
    box.append(banner);
  }

  const sources = result.sources || [];
  const cited = new Set(sources.flatMap((s) => s.numbers));
  const sourceIndex = new Map(); // citation number -> index of its document card
  sources.forEach((s, i) => s.numbers.forEach((n) => sourceIndex.set(n, i)));
  box.append(renderAnswerText(result.answer, msgId, cited, sourceIndex));

  if (sources.length) {
    const cards = el("div", "sources");
    sources.forEach((s, i) => cards.append(sourceCard(s, msgId, i)));
    box.append(cards);
  }

  const meta = el("div", "meta");
  const seconds = (result.timings_ms?.total ?? 0) / 1000;
  meta.append(el("span", "timing", `Answered in ${seconds.toFixed(1)} s`));
  meta.append(feedbackButtons(result.question_id));
  box.append(meta);
}

function renderError(box, message) {
  box.replaceChildren();
  box.classList.add("msg-error");
  const banner = el("div", "error-banner");
  banner.append(el("span", null, "⚠"), el("span", null, message));
  box.append(banner);
}

// --------------------------------------------------------------------- ask

async function ask(question) {
  question = question.trim();
  if (!question || busy) return;
  if (question.length > MAX_CHARS) question = question.slice(0, MAX_CHARS);
  welcome.hidden = true;
  addUserMessage(question);
  input.value = "";
  updateComposer();
  setBusy(true);
  const loading = addLoading();
  scrollToBottom();
  try {
    const result = await postJSON("/api/ask", { question });
    renderAnswer(loading.box, result);
  } catch (error) {
    const message =
      error instanceof TypeError ? "Could not reach the server. Is it running?" : error.message;
    renderError(loading.box, message);
  } finally {
    loading.stop();
    setBusy(false);
    scrollToBottom();
    input.focus();
  }
}

// ---------------------------------------------------------------- composer

function updateComposer() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  const length = input.value.length;
  counter.textContent = `${length}/${MAX_CHARS}`;
  counter.classList.toggle("near-limit", length > MAX_CHARS - 50);
  sendButton.disabled = busy || input.value.trim() === "";
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  ask(input.value);
});

input.addEventListener("input", updateComposer);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    ask(input.value);
  }
});

exampleButtons.forEach((button) =>
  button.addEventListener("click", () => ask(button.textContent))
);

// ------------------------------------------------------------ sources list

let sourcesLoaded = false;

async function loadSources() {
  const list = document.getElementById("source-list");
  const note = document.getElementById("sources-count");
  try {
    const response = await fetch("/api/sources");
    const data = await response.json();
    if (!response.ok) throw new Error(data?.error?.message || "Could not load the sources.");
    note.textContent = `${data.count} official public documents are searched for every answer.`;
    list.replaceChildren(
      ...data.sources.map((source) => {
        const item = el("li");
        const link = el("a", null, source.title);
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        item.append(el("span", "lang-tag", (source.language || "?").toUpperCase()), link);
        return item;
      })
    );
    sourcesLoaded = true;
  } catch (error) {
    note.textContent = error.message;
  }
}

document.getElementById("sources-button").addEventListener("click", () => {
  sourcesDialog.showModal();
  if (!sourcesLoaded) loadSources();
});
document.getElementById("sources-close").addEventListener("click", () => sourcesDialog.close());
sourcesDialog.addEventListener("click", (event) => {
  if (event.target === sourcesDialog) sourcesDialog.close(); // click on the backdrop
});

updateComposer();
input.focus();

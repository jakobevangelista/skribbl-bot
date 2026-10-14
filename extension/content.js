// Reads the live Skribbl hint and canvas, asks the local guess server, and
// fills the chat box when a suggestion is clicked. It never submits the form.
//
// Selectors match the current skribbl.io page:
//   #game-word .description / .word / .hints .container > .hint
//   #game-word .hints .container > .word-length
//   #game-canvas canvas          (one 800x600 canvas)
//   #game-canvas .overlay.show   (choosing a word, reveal, or results)
//   #game-chat input
//   #game-chat-input-mobile input
//   #game-chat .chat-content > p   (b "Name: " + span guess, or a status line)

const MIN_DRAW_INTERVAL_MS = 250;
const MAX_EDGE = 512;

const root = document.createElement("div");
root.id = "skribbl-guesser-root";
const shadow = root.attachShadow({ mode: "open" });
shadow.innerHTML = `
  <style>
    :host { all: initial; }
    .panel {
      position: fixed;
      top: 12px;
      left: 12px;
      z-index: 2147483646;
      width: 240px;
      max-height: 70vh;
      overflow: auto;
      box-sizing: border-box;
      padding: 10px 12px;
      border-radius: 10px;
      background: rgba(12, 16, 32, 0.92);
      color: #f4f6fb;
      font: 13px/1.35 Nunito, sans-serif;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
    }
    .head { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
    .pattern { font-family: Inconsolata, ui-monospace, monospace; font-weight: 700; letter-spacing: 1px; }
    button { font: inherit; color: inherit; cursor: pointer; }
    .collapse, .wrong {
      border: 0;
      background: transparent;
      color: #c5cbe0;
    }
    .status { margin: 6px 0 8px; color: #c5cbe0; }
    ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
    li { display: flex; gap: 4px; }
    .fill {
      flex: 1;
      text-align: left;
      border: 0;
      border-radius: 6px;
      padding: 5px 8px;
      background: #2a3358;
    }
    .fill:hover { background: #3a4678; }
    .section { margin-top: 8px; color: #9aa3bf; }
    .empty { color: #9aa3bf; padding: 2px 0 4px; }
    .hidden { display: none; }
  </style>
  <div class="panel">
    <div class="head">
      <div class="pattern" id="pattern">—</div>
      <button class="collapse" id="collapse" type="button" title="Collapse">–</button>
    </div>
    <div class="status" id="status">Waiting for a round</div>
    <div id="body">
      <ul id="guesses"></ul>
      <div class="section hidden" id="extra-label">Also fits the letters</div>
      <ul id="extra"></ul>
      <div class="section hidden" id="close-label">Ignored, wrong length or letters</div>
      <ul id="close"></ul>
    </div>
  </div>
`;
document.documentElement.appendChild(root);

const patternEl = shadow.getElementById("pattern");
const statusEl = shadow.getElementById("status");
const bodyEl = shadow.getElementById("body");
const guessesEl = shadow.getElementById("guesses");
const extraEl = shadow.getElementById("extra");
const closeEl = shadow.getElementById("close");
const extraLabel = shadow.getElementById("extra-label");
const closeLabel = shadow.getElementById("close-label");
let collapsed = false;

shadow.getElementById("collapse").addEventListener("click", () => {
  collapsed = !collapsed;
  bodyEl.classList.toggle("hidden", collapsed);
  shadow.getElementById("collapse").textContent = collapsed ? "+" : "–";
});

let lastHash = "";
let lastHintKey = "";
let lastRoundKey = "";
let lastRaw = [];
let lastSentAt = 0;
let busy = false;
let chatDirty = false;
let drawingMark = -1;
const rejects = new Set();
const chatRejects = new Set();

function visible(element) {
  if (!element) return false;
  return getComputedStyle(element).display !== "none";
}

function readState() {
  const game = document.querySelector("#game");
  if (!visible(game)) {
    return { phase: "lobby" };
  }
  const overlay = document.querySelector("#game-canvas .overlay");
  if (overlay && overlay.classList.contains("show")) {
    return { phase: "overlay" };
  }
  const word = document.querySelector("#game-word .word");
  const container = document.querySelector("#game-word .hints .container");
  const drawing = word && word.style.display !== "none" && word.textContent.trim().length > 0;
  if (drawing) {
    return { phase: "drawing", answer: word.textContent.trim() };
  }
  if (!container || container.style.display === "none") {
    return { phase: "waiting" };
  }
  const hints = [...container.querySelectorAll(":scope > .hint")].map((el) => el.textContent);
  if (hints.length === 0) {
    return { phase: "waiting" };
  }
  const wordLength = container.querySelector(":scope > .word-length")?.textContent?.trim() || "";
  return { phase: "guessing", hints, wordLength };
}

function captureCanvas() {
  const source = document.querySelector("#game-canvas canvas");
  if (!source || source.width < 2 || source.height < 2) return null;
  const scale = Math.min(1, MAX_EDGE / Math.max(source.width, source.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(source.width * scale));
  canvas.height = Math.max(1, Math.round(source.height * scale));
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(source, 0, 0, canvas.width, canvas.height);
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  let ink = 0;
  let hash = 2166136261;
  for (let i = 0; i < pixels.length; i += 64) {
    const r = pixels[i];
    const g = pixels[i + 1];
    const b = pixels[i + 2];
    if (r < 245 || g < 245 || b < 245) ink += 1;
    hash ^= r;
    hash = Math.imul(hash, 16777619);
  }
  if (ink < 12) return { blank: true };
  return {
    blank: false,
    hash: String(hash >>> 0),
    png: canvas.toDataURL("image/png").split(",")[1],
  };
}

function rejectedWords() {
  return [...rejects, ...chatRejects];
}

// A player guess is <b>Name: </b><span>word</span>. Status lines (joined, left,
// guessed the word, liked the drawing, is close) put the whole sentence in <b>
// and leave the span empty, so they never count as guesses.
function playerGuess(line) {
  const name = line.querySelector("b");
  const body = line.querySelector("span");
  if (!name || !body || !name.textContent.endsWith(": ")) return "";
  return body.textContent.trim().toLowerCase().replace(/\s+/g, " ");
}

function isDrawingNow(line) {
  const body = line.querySelector("span");
  const name = line.querySelector("b");
  if (!name || (body && body.textContent.trim())) return false;
  return /drawing now/i.test(name.textContent);
}

function syncChatRejects() {
  const lines = document.querySelectorAll("#game-chat .chat-content > p");
  let mark = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (isDrawingNow(lines[i])) mark = i + 1;
  }
  if (mark !== drawingMark) {
    drawingMark = mark;
    chatRejects.clear();
    rejects.clear();
    chatDirty = true;
  }
  for (let i = mark; i < lines.length; i += 1) {
    const guess = playerGuess(lines[i]);
    if (!guess || chatRejects.has(guess)) continue;
    chatRejects.add(guess);
    chatDirty = true;
  }
}

function fillChat(word) {
  const inputs = [
    document.querySelector("#game-chat input"),
    document.querySelector("#game-chat-input-mobile input"),
  ].filter(Boolean);
  for (const input of inputs) {
    input.value = word;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
  const focused = inputs.find((input) => input.getClientRects().length > 0) || inputs[0];
  focused?.focus();
}

function renderWords(list, element, kind) {
  element.replaceChildren();
  for (const word of list) {
    const item = document.createElement("li");
    const fill = document.createElement("button");
    fill.type = "button";
    fill.className = "fill";
    fill.textContent = word;
    fill.addEventListener("click", () => fillChat(word));
    item.appendChild(fill);
    if (kind === "guess") {
      const wrong = document.createElement("button");
      wrong.type = "button";
      wrong.className = "wrong";
      wrong.textContent = "×";
      wrong.title = "Hide for this round";
      wrong.addEventListener("click", () => {
        rejects.add(word);
        lastRaw = lastRaw.filter((entry) => entry !== word);
        lastHintKey = "";
        tick();
      });
      item.appendChild(wrong);
    }
    element.appendChild(item);
  }
}

function showResult(payload) {
  if (payload.pattern) {
    patternEl.textContent = payload.pattern === "hidden" ? "???" : payload.pattern;
  }
  if (payload.error) {
    statusEl.textContent = payload.error;
  } else if (payload.model_ms != null) {
    statusEl.textContent = `${payload.guesses.length} fits · ${payload.model_ms} ms`;
  } else {
    statusEl.textContent = `${payload.guesses.length} fits`;
  }
  renderWords(payload.guesses || [], guessesEl, "guess");
  if (!(payload.guesses || []).length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "Nothing fits this pattern yet";
    guessesEl.appendChild(empty);
  }
  renderWords(payload.dictionary || [], extraEl, "extra");
  renderWords(payload.close || [], closeEl, "close");
  extraLabel.classList.toggle("hidden", !(payload.dictionary || []).length);
  closeLabel.classList.toggle("hidden", !(payload.close || []).length);
  if (Array.isArray(payload.raw)) lastRaw = payload.raw;
}

function setStatus(text, pattern) {
  statusEl.textContent = text;
  if (pattern) patternEl.textContent = pattern;
}

async function request(body, quiet) {
  busy = true;
  if (!quiet) setStatus("Looking at the drawing…", patternEl.textContent);
  if (body.image) {
    closeEl.replaceChildren();
    closeLabel.classList.add("hidden");
  }
  try {
    const payload = await chrome.runtime.sendMessage({ type: "guess", body });
    showResult(payload || { error: "No reply from the extension" });
  } catch (error) {
    setStatus(error && error.message ? error.message : "Could not reach the guess server");
  } finally {
    busy = false;
  }
}

function tick() {
  syncChatRejects();
  if (busy) return;
  const state = readState();
  if (state.phase === "lobby") {
    setStatus("Waiting for a game", "—");
    return;
  }
  if (state.phase === "overlay") {
    setStatus("Round is between drawings", patternEl.textContent);
    return;
  }
  if (state.phase === "drawing") {
    setStatus("You are drawing", state.answer);
    guessesEl.replaceChildren();
    extraEl.replaceChildren();
    closeEl.replaceChildren();
    return;
  }
  if (state.phase !== "guessing") {
    setStatus("Waiting for a hint", "—");
    return;
  }

  const roundKey = `${state.hints.length}:${state.wordLength}`;
  if (roundKey !== lastRoundKey) {
    lastRoundKey = roundKey;
    lastRaw = [];
    lastHash = "";
    rejects.clear();
  }
  const hintKey = JSON.stringify([state.hints, state.wordLength]);
  const shot = captureCanvas();
  if (!shot || shot.blank) {
    if (chatDirty) {
      chatDirty = false;
      request(
        {
          hints: state.hints,
          word_length: state.wordLength,
          raw: lastRaw,
          rejects: rejectedWords(),
        },
        true,
      );
    } else {
      setStatus("Waiting for ink on the canvas");
      patternEl.textContent = state.hints.join("");
    }
    return;
  }

  const hintsChanged = hintKey !== lastHintKey;
  const drawingChanged = shot.hash !== lastHash;
  if (!hintsChanged && !drawingChanged && !chatDirty) return;

  patternEl.textContent = state.hints.every((hint) => hint === "?") ? "???" : state.hints.join("");
  if (hintsChanged && !drawingChanged && lastRaw.length) {
    chatDirty = false;
    lastHintKey = hintKey;
    request({
      hints: state.hints,
      word_length: state.wordLength,
      raw: lastRaw,
      rejects: rejectedWords(),
    });
    return;
  }
  if (chatDirty && !drawingChanged) {
    chatDirty = false;
    lastHintKey = hintKey;
    request(
      {
        hints: state.hints,
        word_length: state.wordLength,
        raw: lastRaw,
        rejects: rejectedWords(),
      },
      true,
    );
    return;
  }

  // One look at a time. The next stroke goes out as soon as that look returns.
  if (drawingChanged && Date.now() - lastSentAt < MIN_DRAW_INTERVAL_MS) return;

  lastHash = shot.hash;
  lastHintKey = hintKey;
  lastSentAt = Date.now();
  request({
    image: shot.png,
    hints: state.hints,
    word_length: state.wordLength,
    rejects: rejectedWords(),
  });
  chatDirty = false;
}

const hintRoot = document.querySelector("#game-word") || document.body;
new MutationObserver(() => tick()).observe(hintRoot, {
  subtree: true,
  childList: true,
  characterData: true,
  attributes: true,
});
const chatRoot = document.querySelector("#game-chat .chat-content");
if (chatRoot) {
  new MutationObserver(() => tick()).observe(chatRoot, { childList: true });
}
window.setInterval(tick, 300);
tick();

/**
 * Horizontal rows (tabs, chat pickers, filters) on a desktop mouse:
 * compact ‹ › buttons at an edge that has more content, wheel scrolls sideways,
 * drag to scroll, and fade masks. Touch devices keep native swiping and see no buttons.
 */
const ROWS = ".chips-scroll, .adm-tabs, .adm-filters, .board-picker";
const EDGE = 2;
const mouse = window.matchMedia ? window.matchMedia("(hover: hover) and (pointer: fine)") : { matches: false };

let queued = false;

export function initScrollers(root) {
  if (!root) return;
  const run = () => {
    queued = false;
    root.querySelectorAll(ROWS).forEach(enhance);
  };
  const schedule = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(run);
  };
  new MutationObserver(schedule).observe(root, { childList: true, subtree: true });
  window.addEventListener("resize", () => root.querySelectorAll(".hscroll").forEach(update), { passive: true });
  run();
}

function arrow(dir, row) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = `hs-btn ${dir < 0 ? "hs-prev" : "hs-next"}`;
  btn.tabIndex = -1;
  btn.setAttribute("aria-hidden", "true");
  btn.textContent = dir < 0 ? "‹" : "›";
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    row.scrollBy({ left: dir * Math.max(80, row.clientWidth * 0.8), behavior: "smooth" });
  });
  return btn;
}

function enhance(row) {
  if (row.dataset.hs) return;
  row.dataset.hs = "1";
  const wrap = document.createElement("div");
  wrap.className = "hscroll";
  row.parentNode.insertBefore(wrap, row);
  wrap.appendChild(row);
  wrap.append(arrow(-1, row), arrow(1, row));
  row.addEventListener("scroll", () => update(wrap), { passive: true });
  row.addEventListener(
    "wheel",
    (event) => {
      if (!mouse.matches || event.ctrlKey) return;
      if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return; // trackpads already scroll sideways
      const max = row.scrollWidth - row.clientWidth;
      if (max <= EDGE) return;
      const atStart = row.scrollLeft <= EDGE && event.deltaY < 0;
      const atEnd = row.scrollLeft >= max - EDGE && event.deltaY > 0;
      if (atStart || atEnd) return; // let the page scroll on
      event.preventDefault();
      const step = event.deltaMode === 1 ? event.deltaY * 32 : event.deltaY;
      row.scrollLeft += step;
    },
    { passive: false },
  );
  bindDrag(row);
  if ("ResizeObserver" in window) new ResizeObserver(() => update(wrap)).observe(row);
  update(wrap);
}

function bindDrag(row) {
  let startX = 0;
  let startLeft = 0;
  let pointer = null;
  let moved = false;
  row.addEventListener("pointerdown", (event) => {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    if (row.scrollWidth - row.clientWidth <= EDGE) return;
    pointer = event.pointerId;
    startX = event.clientX;
    startLeft = row.scrollLeft;
    moved = false;
  });
  row.addEventListener("pointermove", (event) => {
    if (pointer !== event.pointerId) return;
    const dx = event.clientX - startX;
    if (!moved && Math.abs(dx) < 6) return;
    if (!moved) {
      moved = true;
      row.classList.add("is-drag");
      try {
        row.setPointerCapture(pointer);
      } catch (_err) {
        /* Capture is best effort. */
      }
    }
    row.scrollLeft = startLeft - dx;
  });
  const end = () => {
    pointer = null;
    row.classList.remove("is-drag");
  };
  row.addEventListener("pointerup", end);
  row.addEventListener("pointercancel", end);
  // A drag must not count as a tap on the chip under the cursor.
  row.addEventListener(
    "click",
    (event) => {
      if (!moved) return;
      moved = false;
      event.preventDefault();
      event.stopPropagation();
    },
    true,
  );
}

function update(wrap) {
  const row = wrap.firstElementChild;
  if (!row) return;
  const max = row.scrollWidth - row.clientWidth;
  wrap.classList.toggle("can-l", max > EDGE && row.scrollLeft > EDGE);
  wrap.classList.toggle("can-r", max > EDGE && row.scrollLeft < max - EDGE);
}

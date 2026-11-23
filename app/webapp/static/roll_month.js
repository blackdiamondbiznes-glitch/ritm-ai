import { api } from "./api.js";
import { groupTabs } from "./group_tabs.js";
import { current, escapeHtml, setHtml, showError, skeleton, t } from "./ui.js";

const TZ = "Asia/Tashkent";
const GLYPH = { present: "✓", late: "●", absent: "×", excused: "○" };

export async function renderMonth(seq) {
  const groupId = Number(hashParts()[2]);
  const month = monthValue();
  setHtml(skeleton("list"));
  try {
    const data = await api(`/api/tutor/groups/${groupId}/attendance?month=${month}`);
    if (!current(seq)) return;
    paint(data, groupId, month);
  } catch (err) {
    if (current(seq)) showError(err);
  }
}

function paint(data, groupId, month) {
  const sessions = data.sessions || [];
  paint.sessions = sessions;
  const students = data.students || [];
  const head = sessions
    .map((row) => `<th>${escapeHtml(short(row.starts_at))}</th>`)
    .join("");
  const body = students.length
    ? students.map((row) => studentLine(row)).join("")
    : `<tr><td colspan="${sessions.length + 2}">${escapeHtml(t("attEmpty"))}</td></tr>`;
  setHtml(`
    ${groupTabs({ id: groupId, name: data.name, weekdays: [], start: "", end: "" }, "roll")}
    <label class="field"><span class="field-label">${escapeHtml(t("attMonth"))}</span>
      <input class="input" id="att-month" type="month" value="${escapeHtml(month)}"></label>
    <div class="card book"><table>
      <thead><tr><th>${escapeHtml(t("grpStudents"))}</th>${head}<th>${escapeHtml(t("attRateWord"))}</th></tr></thead>
      <tbody>${body}</tbody>
    </table></div>
    <p class="stu-meta">${escapeHtml(legend())}</p>
  `);
  document.getElementById("att-month").addEventListener("change", () => {
    const next = document.getElementById("att-month").value;
    if (next) location.hash = `#/cabinet/groups/${groupId}/attendance?month=${next}`;
  });
  document.querySelectorAll("[data-session]").forEach((node) => {
    node.addEventListener("click", () => {
      const id = node.getAttribute("data-session");
      if (id) location.hash = `#/cabinet/schedule/${id}/attendance`;
    });
  });
}

function studentLine(row) {
  const sessions = paint.sessions || [];
  const cells = (row.marks || [])
    .map((status, index) => {
      const id = sessions[index] ? sessions[index].id : "";
      const mark = GLYPH[status] || "·";
      return `<td><button type="button" class="cell-btn" data-session="${id}">${escapeHtml(mark)}</button></td>`;
    })
    .join("");
  return `<tr><th>${escapeHtml(row.name)}</th>${cells}<td>${escapeHtml(percent(row.rate))}</td></tr>`;
}

function legend() {
  return `✓ ${t("attPresent")} · ● ${t("attLate")} · × ${t("attAbsent")} · ○ ${t("attExcused")}`;
}

function percent(rate) {
  if (rate == null) return "—";
  return `${Math.round(rate * 100)}%`;
}

function short(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(iso));
}

function monthValue() {
  const query = (location.hash.split("?")[1] || "").split("&");
  const found = query.map((part) => part.split("=")).find((pair) => pair[0] === "month");
  if (found && found[1]) return found[1];
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit" }).format(new Date());
}

function hashParts() {
  return (location.hash || "").split("?")[0].replace(/^#\/?/, "").split("/").filter(Boolean);
}

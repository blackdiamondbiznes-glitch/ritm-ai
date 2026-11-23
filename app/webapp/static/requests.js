import { api, haptic } from "./api.js";
import { escapeHtml, t } from "./ui.js";

/** Draw the waiting requests on the groups screen and wire the buttons. */
export async function mountRequests(reload) {
  const root = document.getElementById("req-root");
  if (!root) return;
  const data = await api("/api/tutor/requests");
  const rows = data.requests || [];
  const list = rows
    .map(
      (row) => `<div class="stu-row">
        <div class="chat-name">${escapeHtml(row.name)} · ${escapeHtml(row.group_name)}</div>
        <button type="button" class="primary" data-ok="${row.group_id}:${row.student_id}">${escapeHtml(t("reqApprove"))}</button>
        <button type="button" class="ghost" data-no="${row.group_id}:${row.student_id}">${escapeHtml(t("reqReject"))}</button>
      </div>`,
    )
    .join("");
  root.innerHTML = `
    <div class="card-title">${escapeHtml(t("reqTitle", { n: rows.length }))}</div>
    ${list || `<div class="stu-meta">${escapeHtml(t("reqEmpty"))}</div>`}
  `;
  root.querySelectorAll("[data-ok],[data-no]").forEach((node) => {
    node.addEventListener("click", () => {
      const raw = node.getAttribute("data-ok") || node.getAttribute("data-no");
      const [groupId, studentId] = raw.split(":");
      const action = node.hasAttribute("data-ok") ? "approve" : "reject";
      const path = `/api/tutor/requests/${groupId}/${studentId}/${action}`;
      node.disabled = true;
      api(path, { method: "POST", body: "{}" })
        .then(() => {
          haptic("success");
          if (reload) return reload();
          return mountRequests(reload);
        })
        .catch(() => {
          node.disabled = false;
        });
    });
  });
}

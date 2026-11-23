import { go } from "./api.js";
import { t, toast } from "./ui.js";

const PLAN = { free: "Free", start: "Start", pro: "Pro", agency: "Ultra" };
const KEY = {
  limit_groups: "limitGroups",
  limit_students: "limitStudents",
  limit_fees: "limitFees",
  quota: "limitQuota",
  export: "limitExport",
};

/** One upgrade card for every cabinet cap. The button opens the plan screen. */
export function showLimit(err) {
  const code = err && err.code;
  if (!KEY[code]) return false;
  const data = (err && err.data) || {};
  const plan = PLAN[data.plan] || data.plan || "";
  toast(t(KEY[code], { plan, limit: data.limit }), "err");
  mountUpgrade();
  return true;
}

/** Insert the shared card once. Safe to call when the teacher is already at a cap. */
export function mountUpgrade() {
  const main = document.getElementById("main");
  if (!main || document.getElementById("limit-plan")) return;
  const card = document.createElement("div");
  card.className = "card";
  card.id = "limit-card";
  const title = document.createElement("div");
  title.className = "card-title";
  title.textContent = t("limitUpgrade");
  const lead = document.createElement("p");
  lead.className = "stu-meta";
  lead.textContent = t("limitUpgradeLead");
  const button = document.createElement("button");
  button.type = "button";
  button.id = "limit-plan";
  button.className = "primary";
  button.textContent = t("limitPlan");
  button.addEventListener("click", () => go("profile/plan"));
  card.append(title, lead, button);
  main.prepend(card);
}

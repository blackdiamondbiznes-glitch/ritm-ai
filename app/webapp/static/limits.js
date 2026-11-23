import { go } from "./api.js";
import { t, toast } from "./ui.js";

const PLAN = { free: "Free", start: "Start", pro: "Pro", agency: "Ultra" };

/** Show the cabinet cap and a button that opens the plan screen. */
export function showLimit(err) {
  const code = err && err.code;
  if (code !== "limit_groups" && code !== "limit_students" && code !== "limit_fees") return false;
  const data = (err && err.data) || {};
  const plan = PLAN[data.plan] || data.plan || "";
  const key = code === "limit_groups" ? "limitGroups" : code === "limit_fees" ? "limitFees" : "limitStudents";
  toast(t(key, { plan, limit: data.limit }), "err");
  const main = document.getElementById("main");
  if (main && !document.getElementById("limit-plan")) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = "limit-plan";
    button.className = "primary";
    button.textContent = t("limitPlan");
    button.addEventListener("click", () => go("profile/plan"));
    main.prepend(button);
  }
  return true;
}

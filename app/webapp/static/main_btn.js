import { tg } from "./api.js";

let hide = null;

/** Hide Telegram's MainButton. Called on every route change. */
export function clearMainButton() {
  if (hide) {
    hide();
    hide = null;
  }
}

/** Mirror an on-page primary button onto Telegram's MainButton. The page button stays as fallback. */
export function mirrorMainButton(button) {
  clearMainButton();
  const main = tg && tg.MainButton;
  if (!button || !main) return;
  const label = (button.textContent || "").replace(/\s+/g, " ").trim();
  if (!label) return;
  const onClick = () => {
    if (!button.disabled) button.click();
  };
  try {
    if (main.setText) main.setText(label);
    if (main.show) main.show();
    if (main.onClick) main.onClick(onClick);
    hide = () => {
      try {
        if (main.offClick) main.offClick(onClick);
        if (main.hide) main.hide();
      } catch (_err) {
        /* older clients */
      }
    };
  } catch (_err) {
    hide = null;
  }
}

import shellUz from "./i18n_shell_uz.js";
import chatUz from "./i18n_chat_uz.js";
import tutorUz from "./i18n_tutor_uz.js";
import adminUz from "./i18n_admin_uz.js";

export const TIMES = ["08:00", "09:00", "12:00", "18:00", "21:00"];

export const DAYS = {
  uz: { 1: "Du", 2: "Se", 3: "Ch", 4: "Pa", 5: "Ju", 6: "Sh", 7: "Ya" },
  ru: { 1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс" },
  en: { 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun" },
};


export const RESULT = {
  queued: "queued",
  quota: "quota",
  profile: "profileNeed",
  module: "module",
  inactive: "inactive",
  content: "profileNeed",
};

const PACKS = {
  ru: () =>
    Promise.all([
      import("./i18n_shell_ru.js"),
      import("./i18n_chat_ru.js"),
      import("./i18n_tutor_ru.js"),
      import("./i18n_admin_ru.js"),
    ]),
  en: () =>
    Promise.all([
      import("./i18n_shell_en.js"),
      import("./i18n_chat_en.js"),
      import("./i18n_tutor_en.js"),
      import("./i18n_admin_en.js"),
    ]),
};

const cache = {
  uz: { ...shellUz, ...chatUz, ...tutorUz, ...adminUz },
};

let lang = "uz";

function normalize(code) {
  const short = String(code || "uz").slice(0, 2).toLowerCase();
  return short === "ru" || short === "en" || short === "uz" ? short : "uz";
}

/** Load a language pack. Uzbek is already in memory; ru/en are fetched once. */
export async function setLang(code) {
  const next = normalize(code);
  if (!cache[next]) {
    const mods = await PACKS[next]();
    cache[next] = Object.assign({}, ...mods.map((mod) => mod.default));
  }
  lang = next;
  return lang;
}

export function currentLang() {
  return lang;
}

/** o‘/g‘ use U+2018. Any other letter plus an apostrophe is the tutuq sign U+02BC. */
export function normalizeUz(text) {
  return String(text).replace(/([A-Za-z])['\u2019\u2018\u02BC\u02BB`´]/g, (_pair, letter) => {
    const mark = letter.toLowerCase() === "o" || letter.toLowerCase() === "g" ? "\u2018" : "\u02BC";
    return letter + mark;
  });
}

export function t(key, vars) {
  const table = cache[lang] || cache.uz;
  let text = table[key] || cache.uz[key] || key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return lang === "uz" || !cache[lang] ? normalizeUz(text) : text;
}

export function dayLabel(day) {
  const table = DAYS[lang] || DAYS.en;
  return table[day] || String(day);
}

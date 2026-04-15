import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en/common.json";
import zh from "./locales/zh/common.json";
import ja from "./locales/ja/common.json";
import ko from "./locales/ko/common.json";
import es from "./locales/es/common.json";
import fr from "./locales/fr/common.json";
import de from "./locales/de/common.json";

const LS_LANGUAGE = "ws-language";

i18n.use(initReactI18next).init({
  resources: {
    en: { common: en },
    zh: { common: zh },
    ja: { common: ja },
    ko: { common: ko },
    es: { common: es },
    fr: { common: fr },
    de: { common: de },
  },
  lng: localStorage.getItem(LS_LANGUAGE) || "en",
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
  saveMissing: true,
  missingKeyHandler: (_lngs, ns, key) => {
    console.warn(`[i18n] missing key: ${ns}:${key}`);
  },
});

/** Persist language choice and sync with backend settings. */
export function setLanguage(lang: string) {
  localStorage.setItem(LS_LANGUAGE, lang);
  i18n.changeLanguage(lang);
}

/** Supported languages — single source of truth for all language selectors. */
export const LANGUAGES = [
  { code: "en", label: "EN", name: "English" },
  { code: "zh", label: "中", name: "中文" },
  { code: "ja", label: "日", name: "日本語" },
  { code: "ko", label: "한", name: "한국어" },
  { code: "es", label: "ES", name: "Español" },
  { code: "fr", label: "FR", name: "Français" },
  { code: "de", label: "DE", name: "Deutsch" },
] as const;

/** Map i18n language code to the display name used by backend DM. */
export function languageDisplayName(code: string): string {
  const map: Record<string, string> = {
    en: "English",
    zh: "Chinese (中文)",
    ja: "Japanese (日本語)",
    ko: "Korean (한국어)",
    es: "Spanish",
    fr: "French",
    de: "German",
  };
  return map[code] || "English";
}

export { LS_LANGUAGE };
export default i18n;

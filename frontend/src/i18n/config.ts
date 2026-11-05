export const locales = ["fr", "en", "es"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "fr";
export const localeCookieName = "racex_locale";
export const localeStorageKey = "racex_locale";

export const localeMeta: Record<Locale, {
  label: string;
  short: string;
  intl: string;
  htmlLang: string;
  ogLocale: string;
}> = {
  fr: { label: "Français", short: "FR", intl: "fr-FR", htmlLang: "fr", ogLocale: "fr_FR" },
  en: { label: "English", short: "EN", intl: "en-GB", htmlLang: "en", ogLocale: "en_US" },
  es: { label: "Español", short: "ES", intl: "es-ES", htmlLang: "es", ogLocale: "es_ES" },
};

export function isLocale(value: string | null | undefined): value is Locale {
  return Boolean(value) && (locales as readonly string[]).includes(value as string);
}

export function resolveLocale(candidates: readonly string[]): Locale {
  for (const candidate of candidates) {
    const normalized = candidate.trim().toLowerCase();
    if (!normalized) continue;
    const base = normalized.split("-")[0];
    if (isLocale(base)) return base;
  }
  return defaultLocale;
}

"use client";

import { interpolate } from "../i18n/format";
import { locales, localeMeta } from "../i18n/config";
import { useI18n } from "../i18n/provider";

export default function LanguageSwitcher() {
  const { locale, messages, setLocale } = useI18n();

  return (
    <div className="language-switcher" role="group" aria-label={messages.language.label}>
      {locales.map((option) => (
        <button
          key={option}
          type="button"
          className={option === locale ? "selected" : ""}
          aria-pressed={option === locale}
          aria-label={interpolate(messages.language.switchTo, { language: localeMeta[option].label })}
          title={localeMeta[option].label}
          onClick={() => setLocale(option)}
        >
          {localeMeta[option].short}
        </button>
      ))}
    </div>
  );
}

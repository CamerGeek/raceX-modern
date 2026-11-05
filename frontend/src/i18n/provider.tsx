"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { localeCookieName, localeMeta, localeStorageKey, type Locale } from "./config";
import { getMessages, type Messages } from "./index";

type I18nContextValue = {
  locale: Locale;
  messages: Messages;
  intlLocale: string;
  setLocale: (locale: Locale) => void;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({
  initialLocale,
  children,
}: Readonly<{ initialLocale: Locale; children: ReactNode }>) {
  const router = useRouter();
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = localeMeta[locale].htmlLang;
  }, [locale]);

  const setLocale = useCallback((nextLocale: Locale) => {
    document.cookie = `${localeCookieName}=${nextLocale}; path=/; max-age=31536000; samesite=lax`;
    try {
      window.localStorage.setItem(localeStorageKey, nextLocale);
    } catch {
      // Private browsing may block storage; the cookie still carries the choice.
    }
    document.documentElement.lang = localeMeta[nextLocale].htmlLang;
    setLocaleState(nextLocale);
    router.refresh();
  }, [router]);

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    messages: getMessages(locale),
    intlLocale: localeMeta[locale].intl,
    setLocale,
  }), [locale, setLocale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used within I18nProvider");
  return context;
}

export function useMessages(): Messages {
  return useI18n().messages;
}

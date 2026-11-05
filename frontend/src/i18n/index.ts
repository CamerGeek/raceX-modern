import type { Locale } from "./config";
import fr, { type Messages } from "./messages/fr";
import en from "./messages/en";
import es from "./messages/es";

export const messagesByLocale: Record<Locale, Messages> = { fr, en, es };

export function getMessages(locale: Locale): Messages {
  return messagesByLocale[locale];
}

export type { Messages };

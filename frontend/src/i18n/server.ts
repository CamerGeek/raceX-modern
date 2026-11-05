import { cookies, headers } from "next/headers";
import { isLocale, localeCookieName, resolveLocale, type Locale } from "./config";
import { getMessages, type Messages } from "./index";

export async function getRequestLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(localeCookieName)?.value;
  if (isLocale(cookieLocale)) return cookieLocale;

  const headerStore = await headers();
  const acceptLanguage = headerStore.get("accept-language") ?? "";
  return resolveLocale(acceptLanguage.split(",").map((part) => part.split(";")[0]));
}

export async function getRequestMessages(): Promise<{ locale: Locale; messages: Messages }> {
  const locale = await getRequestLocale();
  return { locale, messages: getMessages(locale) };
}

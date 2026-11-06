import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import PwaRegister from "./pwa-register";
import { AuthProvider } from "./auth-context";
import { siteUrl } from "./site-config";
import { I18nProvider } from "../i18n/provider";
import { getRequestMessages } from "../i18n/server";
import { localeMeta } from "../i18n/config";
import { interpolate } from "../i18n/format";

export async function generateMetadata(): Promise<Metadata> {
  const { locale, messages } = await getRequestMessages();

  return {
    metadataBase: new URL(siteUrl),
    title: {
      default: messages.meta.title,
      template: "%s | RaceX",
    },
    description: messages.meta.description,
    applicationName: "RaceX",
    openGraph: {
      type: "website",
      locale: localeMeta[locale].ogLocale,
      siteName: "RaceX",
      title: messages.meta.title,
      description: messages.meta.description,
      url: "/",
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: messages.meta.ogAlt }],
    },
    twitter: {
      card: "summary_large_image",
      title: messages.meta.title,
      description: messages.meta.description,
      images: ["/opengraph-image"],
    },
    manifest: "/manifest.webmanifest",
    icons: {
      icon: [
        { url: "/icons/icon-192.5744981e.png", sizes: "192x192", type: "image/png" },
        { url: "/icons/icon-512.ea14e0ae.png", sizes: "512x512", type: "image/png" },
      ],
      shortcut: "/icons/icon-96.bc021766.png",
      apple: [{ url: "/apple-touch-icon.9768d4b5.png", sizes: "180x180", type: "image/png" }],
    },
    appleWebApp: {
      capable: true,
      title: "RaceX",
      statusBarStyle: "default",
    },
  };
}

export const viewport: Viewport = {
  themeColor: "#103b32",
  colorScheme: "light",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const { locale, messages } = await getRequestMessages();

  return (
    <html lang={localeMeta[locale].htmlLang}>
      <body>
        <I18nProvider initialLocale={locale}>
          <AuthProvider>
            <PwaRegister />
            {children}
            <footer className="site-footer">
              <p>
                {interpolate(messages.footer.rights, { year: new Date().getFullYear() })}{" "}
                <Link href="/privacy">{messages.footer.privacy}</Link>
              </p>
            </footer>
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}

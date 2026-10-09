import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";
import PwaRegister from "./pwa-register";
import { AuthProvider } from "./auth-context";
import { siteUrl } from "./site-config";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "RaceX — Analyse des courses hippiques",
    template: "%s | RaceX",
  },
  description: "Partants du Quinté+, analyses hippiques et repères pour suivre les courses du jour.",
  applicationName: "RaceX",
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: "RaceX",
    title: "RaceX — Analyse des courses hippiques",
    description: "Partants du Quinté+, analyses hippiques et repères pour suivre les courses du jour.",
    url: "/",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RaceX — Analyse des courses hippiques" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "RaceX — Analyse des courses hippiques",
    description: "Partants du Quinté+, analyses hippiques et repères pour suivre les courses du jour.",
    images: ["/opengraph-image"],
  },
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.png", sizes: "any" },
    ],
    shortcut: "/icon.svg",
    apple: "/apple-touch-icon.png",
  },
  appleWebApp: {
    capable: true,
    title: "RaceX",
    statusBarStyle: "default",
  },
};

export const viewport: Viewport = {
  themeColor: "#103b32",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr"><body><AuthProvider><PwaRegister />{children}<footer className="site-footer"><p>© {new Date().getFullYear()} RaceX · Georges BODIONG · <Link href="/privacy">Confidentialité et données personnelles</Link></p></footer></AuthProvider></body></html>
  );
}

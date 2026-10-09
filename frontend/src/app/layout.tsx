import type { Metadata, Viewport } from "next";
import "./globals.css";
import PwaRegister from "./pwa-register";
import { AuthProvider } from "./auth-context";

export const metadata: Metadata = {
  title: "RaceX Analysis Desk",
  description: "Horse racing analysis and handicap intelligence.",
  applicationName: "RaceX",
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
    <html lang="fr"><body><AuthProvider><PwaRegister />{children}</AuthProvider></body></html>
  );
}

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RaceX Analysis Desk",
  description: "Horse racing analysis and handicap intelligence.",
  icons: {
    icon: "/favicon.png",
    shortcut: "/favicon.png",
    apple: "/favicon.png",
  },
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en"><body>{children}</body></html>
  );
}

import type { MetadataRoute } from "next";
import { localeMeta } from "../i18n/config";
import { getRequestMessages } from "../i18n/server";

export default async function manifest(): Promise<MetadataRoute.Manifest> {
  const { locale, messages } = await getRequestMessages();
  const t = messages.pwa;

  const shortcutIcon = [{ src: "/icons/icon-96.bc021766.png", sizes: "96x96", type: "image/png" }];

  return {
    id: "/",
    name: t.name,
    short_name: t.shortName,
    description: t.description,
    lang: localeMeta[locale].htmlLang,
    dir: "ltr",
    start_url: "/",
    scope: "/",
    display: "standalone",
    display_override: ["window-controls-overlay", "standalone", "minimal-ui"],
    orientation: "any",
    background_color: "#f3f0e8",
    theme_color: "#103b32",
    categories: ["sports", "news"],
    icons: [
      { src: "/icons/icon-192.5744981e.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.ea14e0ae.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-192.d40add57.png", sizes: "192x192", type: "image/png", purpose: "maskable" },
      { src: "/icons/maskable-512.4367dffc.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
      { src: "/icons/monochrome-512.d8fd5d4f.png", sizes: "512x512", type: "image/png", purpose: "monochrome" },
    ],
    shortcuts: [
      { name: t.shortcutToday, url: "/", icons: shortcutIcon },
      { name: t.shortcutAccount, url: "/account", icons: shortcutIcon },
      { name: t.shortcutSubscribers, url: "/subscribers", icons: shortcutIcon },
    ],
  };
}

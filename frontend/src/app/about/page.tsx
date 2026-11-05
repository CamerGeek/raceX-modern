import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";
import { localeMeta } from "../../i18n/config";
import { getRequestMessages } from "../../i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { locale, messages } = await getRequestMessages();
  return {
    title: messages.meta.aboutTitle,
    description: messages.meta.aboutDescription,
    alternates: { canonical: "/about" },
    openGraph: {
      type: "website",
      locale: localeMeta[locale].ogLocale,
      siteName: "RaceX",
      title: messages.meta.aboutTitle,
      description: messages.meta.aboutDescription,
      url: "/about",
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: messages.meta.ogAlt }],
    },
    twitter: {
      card: "summary_large_image",
      title: messages.meta.aboutTitle,
      description: messages.meta.aboutDescription,
      images: ["/opengraph-image"],
    },
  };
}

export default async function AboutPage() {
  const { messages } = await getRequestMessages();
  const t = messages.about;

  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="about" />
      <article className="public-widget legal-card">
        <p className="public-kicker">{t.kicker}</p>
        <h1>{t.title}</h1>
        <p>{t.intro}</p>

        <h2>{t.todayTitle}</h2>
        <p>{t.todayBody}</p>

        <h2>{t.analysisTitle}</h2>
        <p>{t.analysisBody}</p>
        <p>{t.caution}</p>

        <h2>{t.independentTitle}</h2>
        <p>
          {t.independentBody}{" "}
          <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> {t.emailJoin}{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>.
        </p>

        <p className="about-links">
          <Link href="/faq">{t.faqLink}</Link>
          {" · "}
          <Link href="/account">{t.accountLink}</Link>
        </p>
      </article>
    </main>
  );
}

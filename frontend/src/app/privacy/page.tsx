import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";
import { localeMeta } from "../../i18n/config";
import { getRequestMessages } from "../../i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { locale, messages } = await getRequestMessages();
  return {
    title: messages.meta.privacyTitle,
    description: messages.meta.privacyDescription,
    alternates: { canonical: "/privacy" },
    robots: { index: true, follow: true },
    openGraph: {
      type: "website",
      locale: localeMeta[locale].ogLocale,
      siteName: "RaceX",
      title: messages.meta.privacyTitle,
      description: messages.meta.privacyDescription,
      url: "/privacy",
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: messages.meta.ogAlt }],
    },
    twitter: {
      card: "summary_large_image",
      title: messages.meta.privacyTitle,
      description: messages.meta.privacyDescription,
      images: ["/opengraph-image"],
    },
  };
}

export default async function PrivacyPage() {
  const { messages } = await getRequestMessages();
  const t = messages.privacy;

  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="home" />
      <article className="public-widget legal-card">
        <p className="public-kicker">{t.kicker}</p>
        <h1>{t.title}</h1>
        <p className="legal-updated">{t.updated}</p>

        <p>{t.intro}</p>

        <h2>{t.contactTitle}</h2>
        <p>
          {t.contactBefore}{" "}
          <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> {t.emailJoin}{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>{t.contactAfter}
        </p>

        <h2>{t.dataTitle}</h2>
        <ul>
          <li>
            <strong>{t.dataAccountLabel}</strong> {t.dataAccount}
          </li>
          <li>
            <strong>{t.dataSubscriptionLabel}</strong> {t.dataSubscription}
          </li>
          <li>
            <strong>{t.dataUsageLabel}</strong> {t.dataUsage}
          </li>
        </ul>

        <h2>{t.purposesTitle}</h2>
        <p>{t.purposesOne}</p>
        <p>{t.purposesTwo}</p>

        <h2>{t.cookiesTitle}</h2>
        <p>{t.cookiesBody}</p>

        <h2>{t.retentionTitle}</h2>
        <p>{t.retentionOne}</p>
        <p>{t.retentionTwo}</p>

        <h2>{t.updatesTitle}</h2>
        <p>{t.updatesBody}</p>
        <p><Link href="/">{t.backHome}</Link></p>
      </article>
    </main>
  );
}

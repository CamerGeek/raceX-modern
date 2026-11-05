import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";
import { localeMeta } from "../../i18n/config";
import { getRequestMessages } from "../../i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { locale, messages } = await getRequestMessages();
  return {
    title: messages.meta.faqTitle,
    description: messages.meta.faqDescription,
    alternates: { canonical: "/faq" },
    openGraph: {
      type: "website",
      locale: localeMeta[locale].ogLocale,
      siteName: "RaceX",
      title: messages.meta.faqTitle,
      description: messages.meta.faqDescription,
      url: "/faq",
      images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: messages.meta.ogAlt }],
    },
    twitter: {
      card: "summary_large_image",
      title: messages.meta.faqTitle,
      description: messages.meta.faqDescription,
      images: ["/opengraph-image"],
    },
  };
}

export default async function FaqPage() {
  const { messages } = await getRequestMessages();
  const t = messages.faq;

  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="faq" />
      <article className="public-widget legal-card">
        <p className="public-kicker">{t.kicker}</p>
        <h1>{t.title}</h1>
        <p>{t.intro}</p>

        <div className="faq-list">
          {t.questions.map(({ question, answer }) => (
            <details className="faq-item" key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>

        <p>
          {t.contact}{" "}
          <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> {t.emailJoin}{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>.
        </p>
        <p><Link href="/about">{t.aboutLink}</Link></p>
      </article>
    </main>
  );
}

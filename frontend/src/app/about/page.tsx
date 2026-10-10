import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";

export const metadata: Metadata = {
  title: "À propos de RaceX",
  description: "Découvrez RaceX, un espace francophone dédié au Quinté+ et à l’analyse des courses hippiques.",
  alternates: { canonical: "/about" },
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: "RaceX",
    title: "À propos de RaceX",
    description: "Découvrez RaceX, un espace francophone dédié au Quinté+ et à l’analyse des courses hippiques.",
    url: "/about",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RaceX — Analyse des courses hippiques" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "À propos de RaceX",
    description: "Découvrez RaceX, un espace francophone dédié au Quinté+ et à l’analyse des courses hippiques.",
    images: ["/opengraph-image"],
  },
};

export default function AboutPage() {
  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="about" />
      <article className="public-widget legal-card">
        <p className="public-kicker">RACEX · À PROPOS</p>
        <h1>Comprendre les courses, avec plus de repères</h1>
        <p>
          RaceX est un service francophone consacré aux courses hippiques, conçu pour aider les
          passionnés à consulter les partants du Quinté+ et à explorer des analyses de course au
          même endroit.
        </p>

        <h2>Les courses du jour</h2>
        <p>
          La page d’accueil rassemble les partants du Quinté+, des repères de sélection et des
          informations de résultats. Certains contenus de courses sont intégrés depuis Zone-Turf ;
          les données de course et les cotes sont susceptibles d’évoluer.
        </p>

        <h2>Des analyses pour éclairer votre lecture</h2>
        <p>
          L’espace RaceX propose, selon la course et les données disponibles, des synthèses et des
          indicateurs pour comparer les partants. Un compte donne accès à une période de démo de
          sept jours. L’abonnement est proposé à 10 000 FCFA par mois et les paiements confirmés
          sont traités par Chariow.
        </p>
        <p>
          Ces analyses sont des outils d’aide à la lecture, et non des certitudes ou des conseils
          financiers. Les courses comportent des risques ; chacun reste responsable de ses choix.
        </p>

        <h2>Une initiative indépendante</h2>
        <p>
          RaceX est édité et développé par Georges BODIONG, actuellement établi au Burkina Faso.
          Pour les questions sur le service ou votre compte, écrivez à{" "}
          <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> ou{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>.
        </p>

        <p className="about-links">
          <Link href="/faq">Consulter les questions fréquentes</Link>
          {" · "}
          <Link href="/account">Créer un compte ou se connecter</Link>
        </p>
      </article>
    </main>
  );
}

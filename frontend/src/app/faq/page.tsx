import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";

export const metadata: Metadata = {
  title: "Questions fréquentes",
  description: "Réponses aux questions fréquentes sur les comptes, la démo, les analyses et les paiements RaceX.",
  alternates: { canonical: "/faq" },
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: "RaceX",
    title: "Questions fréquentes sur RaceX",
    description: "Réponses aux questions fréquentes sur les comptes, la démo, les analyses et les paiements RaceX.",
    url: "/faq",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RaceX — Analyse des courses hippiques" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Questions fréquentes sur RaceX",
    description: "Réponses aux questions fréquentes sur les comptes, la démo, les analyses et les paiements RaceX.",
    images: ["/opengraph-image"],
  },
};

const questions = [
  {
    question: "Que puis-je consulter sans compte ?",
    answer:
      "L’accueil public affiche les partants du Quinté+ et des informations de course fournies notamment par Zone-Turf. L’analyse complète de RaceX nécessite un compte avec un accès démo ou un abonnement actif.",
  },
  {
    question: "Comment fonctionne la période de démo ?",
    answer:
      "La création d’un compte active une période de démo de sept jours pour les fonctions abonnés. Connectez-vous ensuite à votre compte pour consulter votre niveau d’accès et sa date d’expiration.",
  },
  {
    question: "Combien coûte l’abonnement ?",
    answer:
      "L’abonnement est proposé à 10 000 FCFA par mois. Chaque paiement confirmé ajoute un mois d’accès RaceX ; les paiements sont traités sur la plateforme Chariow.",
  },
  {
    question: "Quand mon accès est-il activé après un paiement ?",
    answer:
      "RaceX active l’abonnement après réception et vérification de la confirmation de paiement. Le retour vers le site ne confirme pas à lui seul le paiement. Si votre accès n’est pas encore à jour, attendez quelques instants puis actualisez la page de votre compte.",
  },
  {
    question: "Les partants, les cotes et les analyses sont-ils définitifs ?",
    answer:
      "Non. Les partants et les cotes peuvent évoluer. Les analyses dépendent des données disponibles au moment de leur consultation et ne garantissent pas le résultat d’une course.",
  },
  {
    question: "Les analyses RaceX garantissent-elles un gain ?",
    answer:
      "Non. Les indicateurs sont des repères d’analyse, pas des certitudes ni une promesse de gain. Les courses comportent des risques ; chacun reste responsable de ses choix.",
  },
  {
    question: "Comment demander de l’aide ou gérer mes données ?",
    answer:
      "Pour une question sur votre compte, un paiement ou vos données personnelles, contactez Georges BODIONG à deebodiong@gmail.com ou gbodiong@yahoo.de. Vous pouvez aussi consulter la page Confidentialité et données personnelles.",
  },
];

export default function FaqPage() {
  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="faq" />
      <article className="public-widget legal-card">
        <p className="public-kicker">RACEX · AIDE</p>
        <h1>Questions fréquentes</h1>
        <p>Les réponses aux questions les plus fréquentes sur RaceX, les comptes et les analyses.</p>

        <div className="faq-list">
          {questions.map(({ question, answer }) => (
            <details className="faq-item" key={question}>
              <summary>{question}</summary>
              <p>{answer}</p>
            </details>
          ))}
        </div>

        <p>
          Vous avez encore une question ? Écrivez à{" "}
          <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> ou{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>.
        </p>
        <p><Link href="/about">En savoir plus sur RaceX</Link></p>
      </article>
    </main>
  );
}

import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";

export const metadata: Metadata = {
  title: "Questions fréquentes",
  description: "Réponses sur les comptes, les paiements et la façon dont RaceX construit ses pronostics, sélections de modèles et votes.",
  alternates: { canonical: "/faq" },
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: "RaceX",
    title: "Questions fréquentes sur RaceX",
    description: "Réponses sur les comptes, les paiements et la façon dont RaceX construit ses pronostics, sélections de modèles et votes.",
    url: "/faq",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RaceX — Analyse des courses hippiques" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Questions fréquentes sur RaceX",
    description: "Réponses sur les comptes, les paiements et la façon dont RaceX construit ses pronostics, sélections de modèles et votes.",
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
      "Vous pouvez choisir une formule hebdomadaire à 2 500 FCFA (7 jours), mensuelle à 8 000 FCFA (1 mois) ou annuelle à 80 000 FCFA (1 an). Chaque paiement confirmé ajoute la durée correspondante à votre accès RaceX. Les paiements sont traités sur Chariow.",
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
    question: "Comment le Pronostic (Prono Flash) est-il établi ?",
    answer:
      "Pour les courses plates et les obstacles, RaceX compare les classements de forme (IF), de classe (IC) et de coefficient de réussite (S_COEFF). Les chevaux présents dans la moitié supérieure des trois classements sont prioritaires, puis ceux présents dans deux ; des chevaux repérés par un seul classement peuvent compléter la sélection, jusqu’à huit. Au trot, le pronostic repose sur sept indicateurs pondérés : coefficient de réussite (20 %), forme/fitness (15 %), tendance de forme (15 %), risque de disqualification (20 %), cote (15 %), courses récentes (10 %) et ferrure (5 %). Les indicateurs disponibles contribuent au score des chevaux qui figurent dans leur première moitié de classement.",
  },
  {
    question: "Comment le Model Shortlist est-il choisi ?",
    answer:
      "Il s’agit d’un classement distinct du Pronostic : le modèle d’apprentissage automatique classe les chevaux par score Deep décroissant et affiche jusqu’à huit chevaux. Ces scores servent à classer les partants ; ce ne sont pas des probabilités de victoire ou de placé calibrées.",
  },
  {
    question: "Que signifie le Priority Tier du modèle ?",
    answer:
      "Le Priority Tier indique l’ordre dans lequel les règles de sélection du modèle retiennent les chevaux ; Tier 1 est prioritaire. Au trot et en obstacles, Tier 1 correspond à au moins trois votes de sources de modèles, Tier 2 à deux votes, puis les places restantes sont complétées par le score moyen de placé. En plat, Tier 1 regroupe les chevaux ayant au moins trois votes, Tier 2 les deux meilleurs par S_COEFF (ou par score moyen de placé si S_COEFF manque), Tier 3 le meilleur score « dark horse », Tier 4 les autres chevaux ayant deux votes, et Tier 5 complète selon le score moyen de placé. La sélection est plafonnée à six chevaux. Les tiers sont une règle de shortlist, pas des probabilités ni une prédiction garantie de l’ordre d’arrivée. Un cheval sans tier n’a pas été retenu dans cette sélection.",
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

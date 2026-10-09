import type { Metadata } from "next";
import Link from "next/link";
import SiteNavigation from "../site-navigation";

export const metadata: Metadata = {
  title: "Confidentialité et données personnelles",
  description: "Comment RaceX utilise, protège et conserve les données liées à votre compte.",
  alternates: { canonical: "/privacy" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    locale: "fr_FR",
    siteName: "RaceX",
    title: "Confidentialité et données personnelles",
    description: "Comment RaceX utilise, protège et conserve les données liées à votre compte.",
    url: "/privacy",
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: "RaceX — Analyse des courses hippiques" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Confidentialité et données personnelles",
    description: "Comment RaceX utilise, protège et conserve les données liées à votre compte.",
    images: ["/opengraph-image"],
  },
};

export default function PrivacyPage() {
  return (
    <main className="shell legal-page">
      <SiteNavigation currentPage="home" />
      <article className="public-widget legal-card">
        <p className="public-kicker">RACEX · INFORMATIONS LÉGALES</p>
        <h1>Confidentialité et données personnelles</h1>
        <p className="legal-updated">Dernière mise à jour : 9 octobre 2026</p>

        <p>
          RaceX est un service édité et développé par Georges BODIONG, actuellement établi au
          Burkina Faso. Cette page explique quelles données sont utilisées pour fournir le service,
          pourquoi elles le sont et comment exercer vos demandes relatives à vos données.
        </p>

        <h2>Responsable et contact</h2>
        <p>
          Pour toute question ou demande concernant vos données personnelles, contactez Georges
          BODIONG à <a href="mailto:deebodiong@gmail.com">deebodiong@gmail.com</a> ou{" "}
          <a href="mailto:gbodiong@yahoo.de">gbodiong@yahoo.de</a>.
        </p>

        <h2>Données utilisées</h2>
        <ul>
          <li>
            <strong>Compte :</strong> adresse e-mail, numéro de téléphone, identifiant de compte
            et informations nécessaires à la gestion de l’accès (démo, abonnement et dates
            d’expiration).
          </li>
          <li>
            <strong>Abonnement :</strong> les informations fournies lors du paiement, comme le nom
            et le numéro de téléphone, ainsi que les confirmations nécessaires à l’activation de
            l’accès. Le paiement est traité par Chariow ; RaceX ne reçoit pas les données complètes
            de votre carte bancaire.
          </li>
          <li>
            <strong>Utilisation du service :</strong> les requêtes nécessaires pour afficher les
            courses et fournir les analyses, ainsi que les données techniques traitées par les
            hébergeurs pour transmettre et sécuriser le service.
          </li>
        </ul>

        <h2>Finalités et prestataires</h2>
        <p>
          Ces données servent à créer et sécuriser votre compte, fournir les fonctions de RaceX,
          gérer les accès de démonstration et les abonnements, répondre aux demandes d’assistance
          et maintenir le service. L’authentification et les profils utilisent Supabase ; le site
          est hébergé sur Vercel et son API sur Render ; Chariow traite les paiements. Les widgets
          de courses affichés sur l’accueil sont fournis par Zone-Turf. Ces prestataires peuvent
          traiter des données techniques ou de compte pour fournir leurs services et selon leurs
          propres politiques de confidentialité.
        </p>
        <p>
          Les prestataires peuvent traiter certaines données hors du Burkina Faso. Consultez leurs
          politiques pour connaître leurs pratiques et les modalités de traitement applicables à
          leurs services.
        </p>

        <h2>Cookies et stockage local</h2>
        <p>
          RaceX n’intègre actuellement ni outil publicitaire ni outil de mesure d’audience. La
          connexion utilise le stockage local du navigateur pour conserver votre session ; le
          service worker de l’application peut également conserver des ressources statiques afin
          d’afficher l’application hors connexion. Ces fonctions sont nécessaires au service.
          Aucun bandeau de consentement publicitaire n’est donc utilisé. Les contenus tiers,
          notamment les widgets Zone-Turf, peuvent être soumis aux pratiques et réglages de leur
          fournisseur.
        </p>

        <h2>Durée de conservation et demandes</h2>
        <p>
          Les informations de compte et d’accès sont conservées tant que le compte ou les droits
          associés sont nécessaires au fonctionnement de RaceX. Certaines informations peuvent
          être conservées plus longtemps lorsqu’elles sont nécessaires au suivi d’un paiement, au
          respect d’obligations applicables ou à la sécurité du service. Les journaux techniques
          peuvent aussi être conservés par les prestataires selon leurs propres politiques.
        </p>
        <p>
          Vous pouvez demander l’accès à vos données, leur rectification ou leur suppression, et
          poser une question sur leur traitement en écrivant à l’une des adresses indiquées
          ci-dessus. Pour protéger votre compte, une vérification raisonnable de votre identité
          pourra être nécessaire. Les demandes sont traitées sous réserve des obligations légales
          applicables.
        </p>

        <h2>Mises à jour</h2>
        <p>
          Cette page peut être mise à jour si le fonctionnement de RaceX ou ses prestataires
          changent. La date en haut de page indique sa dernière révision.
        </p>
        <p><Link href="/">Retour à l’accueil RaceX</Link></p>
      </article>
    </main>
  );
}

import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Page introuvable",
  description: "La page demandée est introuvable. Retrouvez les courses du jour sur RaceX.",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <main className="not-found-page">
      <p className="public-kicker">RACEX · ERREUR 404</p>
      <h1>Cette page n’existe pas</h1>
      <p>Le lien est peut-être incorrect ou la page a été déplacée.</p>
      <Link href="/">Retour aux courses du jour</Link>
    </main>
  );
}

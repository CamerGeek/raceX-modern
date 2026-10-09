"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuth, type AccessRole } from "./auth-context";

export default function AccessGate({
  allowedRoles,
  children,
}: {
  allowedRoles: AccessRole[];
  children: ReactNode;
}) {
  const { loading, profile, session, configured, profileError } = useAuth();

  if (loading) {
    return <main className="shell"><section className="subscriber-state" role="status">Vérification de votre accès…</section></main>;
  }
  if (!session) {
    return (
      <main className="shell">
        <section className="subscriber-state access-gate">
          <h1>Connectez-vous pour accéder à cette page</h1>
          <p>Créez un compte pour bénéficier de votre période de démonstration de 7 jours.</p>
          {!configured && <p role="alert">L’authentification doit être configurée par l’administrateur.</p>}
          <Link className="subscriber-refresh access-gate-link" href="/account">Créer un compte ou se connecter</Link>
        </section>
      </main>
    );
  }
  if (!profile) {
    return (
      <main className="shell">
        <section className="subscriber-state subscriber-error" role="alert">
          <p>{profileError || "Votre profil n’est pas disponible. Réessayez ou contactez l’administrateur."}</p>
          <Link href="/account">Mon compte</Link>
        </section>
      </main>
    );
  }
  if (!allowedRoles.includes(profile.role)) {
    return (
      <main className="shell">
        <section className="subscriber-state access-gate">
          <h1>Accès réservé</h1>
          <p>
            {profile.role === "simple"
              ? "Votre période d’accès démo est terminée. Contactez l’administrateur pour demander l’activation d’un abonnement."
              : "Votre compte ne dispose pas des droits nécessaires pour consulter cette page."}
          </p>
          <Link className="subscriber-refresh access-gate-link" href="/account">
            Voir les options d’abonnement
          </Link>
        </section>
      </main>
    );
  }
  return children;
}

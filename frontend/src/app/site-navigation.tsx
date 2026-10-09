"use client";

import Link from "next/link";
import { useAuth } from "./auth-context";

type SiteNavigationProps = {
  currentPage: "home" | "analysis" | "subscribers" | "account" | "user-admin";
};

export default function SiteNavigation({ currentPage }: SiteNavigationProps) {
  const { profile, session, signOut } = useAuth();
  const canViewSubscribers = profile && ["demo", "subscriber", "admin"].includes(profile.role);
  const isAdmin = profile?.role === "admin";

  return (
    <nav className="site-navigation" aria-label="Navigation principale">
      <Link href="/" aria-current={currentPage === "home" ? "page" : undefined}>
        Quinté du jour
      </Link>
      {canViewSubscribers && (
        <Link href="/subscribers" aria-current={currentPage === "subscribers" ? "page" : undefined}>
          Espace abonnés
        </Link>
      )}
      {isAdmin && (
        <>
          <Link href="/admin" aria-current={currentPage === "analysis" ? "page" : undefined}>
            Analyse des courses
          </Link>
          <Link href="/admin/users" aria-current={currentPage === "user-admin" ? "page" : undefined}>
            Gestion des comptes
          </Link>
        </>
      )}
      <Link href="/account" aria-current={currentPage === "account" ? "page" : undefined}>
        {session ? "Mon compte" : "Connexion / Démo"}
      </Link>
      {session && <button type="button" className="site-navigation-signout" onClick={() => void signOut()}>Déconnexion</button>}
    </nav>
  );
}

"use client";

import Link from "next/link";
import { useAuth } from "./auth-context";
import LanguageSwitcher from "./language-switcher";
import { useMessages } from "../i18n/provider";

type SiteNavigationProps = {
  currentPage: "home" | "about" | "faq" | "analysis" | "subscribers" | "account" | "user-admin";
};

export default function SiteNavigation({ currentPage }: SiteNavigationProps) {
  const { profile, session, signOut } = useAuth();
  const t = useMessages();
  const canViewSubscribers = profile && ["demo", "subscriber", "admin"].includes(profile.role);
  const isAdmin = profile?.role === "admin";

  return (
    <nav className="site-navigation" aria-label={t.nav.aria}>
      <Link href="/" aria-current={currentPage === "home" ? "page" : undefined}>
        {t.nav.home}
      </Link>
      <Link href="/about" aria-current={currentPage === "about" ? "page" : undefined}>
        {t.nav.about}
      </Link>
      <Link href="/faq" aria-current={currentPage === "faq" ? "page" : undefined}>
        {t.nav.faq}
      </Link>
      {canViewSubscribers && (
        <Link href="/subscribers" aria-current={currentPage === "subscribers" ? "page" : undefined}>
          {t.nav.subscribers}
        </Link>
      )}
      {isAdmin && (
        <>
          <Link href="/admin" aria-current={currentPage === "analysis" ? "page" : undefined}>
            {t.nav.analysis}
          </Link>
          <Link href="/admin/users" aria-current={currentPage === "user-admin" ? "page" : undefined}>
            {t.nav.userAdmin}
          </Link>
        </>
      )}
      <Link href="/account" aria-current={currentPage === "account" ? "page" : undefined}>
        {session ? t.nav.account : t.nav.signIn}
      </Link>
      <LanguageSwitcher />
      {session && <button type="button" className="site-navigation-signout" onClick={() => void signOut()}>{t.nav.signOut}</button>}
    </nav>
  );
}

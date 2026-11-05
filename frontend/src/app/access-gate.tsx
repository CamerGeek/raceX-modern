"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useAuth, type AccessRole } from "./auth-context";
import { useMessages } from "../i18n/provider";

export default function AccessGate({
  allowedRoles,
  children,
}: {
  allowedRoles: AccessRole[];
  children: ReactNode;
}) {
  const { loading, offlineAccess, profile, session, configured, profileError } = useAuth();
  const t = useMessages().accessGate;

  if (loading) {
    return <main className="shell"><section className="subscriber-state" role="status">{t.checking}</section></main>;
  }
  if (!session && !offlineAccess) {
    return (
      <main className="shell">
        <section className="subscriber-state access-gate">
          <h1>{t.signInTitle}</h1>
          <p>{t.signInBody}</p>
          {!configured && <p role="alert">{t.notConfigured}</p>}
          <Link className="subscriber-refresh access-gate-link" href="/account">{t.signInCta}</Link>
        </section>
      </main>
    );
  }
  if (!profile) {
    return (
      <main className="shell">
        <section className="subscriber-state subscriber-error" role="alert">
          <p>{profileError || t.profileUnavailable}</p>
          <Link href="/account">{t.account}</Link>
        </section>
      </main>
    );
  }
  if (!allowedRoles.includes(profile.role)) {
    return (
      <main className="shell">
        <section className="subscriber-state access-gate">
          <h1>{t.restrictedTitle}</h1>
          <p>{profile.role === "simple" ? t.demoExpired : t.noRights}</p>
          <Link className="subscriber-refresh access-gate-link" href="/account">
            {t.options}
          </Link>
        </section>
      </main>
    );
  }
  return children;
}

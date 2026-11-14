"use client";

import type { ReactNode } from "react";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMessages } from "../i18n/provider";
import { useAuth } from "./auth-context";

export default function HomeAuthRedirect({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { loading, session } = useAuth();
  const checkingMessage = useMessages().accessGate.checking;

  useEffect(() => {
    if (!loading && session) {
      router.replace("/subscribers");
    }
  }, [loading, router, session]);

  if (loading || session) {
    return (
      <main className="shell">
        <section className="subscriber-state" role="status">{checkingMessage}</section>
      </main>
    );
  }

  return children;
}

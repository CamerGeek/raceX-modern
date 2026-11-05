"use client";

import Link from "next/link";
import { useMessages } from "../i18n/provider";

export default function NotFound() {
  const t = useMessages().notFound;

  return (
    <main className="not-found-page">
      <p className="public-kicker">{t.kicker}</p>
      <h1>{t.title}</h1>
      <p>{t.body}</p>
      <Link href="/">{t.backHome}</Link>
    </main>
  );
}

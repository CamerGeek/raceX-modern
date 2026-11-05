"use client";

import Link from "next/link";
import { useMessages } from "../../i18n/provider";

export default function OfflinePage() {
  const t = useMessages().offline;

  return (
    <main className="offline-page">
      <section>
        <span className="offline-mark" aria-hidden="true">RX</span>
        <p className="offline-kicker">{t.kicker}</p>
        <h1>{t.title}</h1>
        <p>{t.body}</p>
        <form action="/offline" method="get">
          <button type="submit">{t.retry}</button>
        </form>
        <p className="offline-links">
          <Link href="/subscribers">{t.savedData}</Link>
          {" · "}
          <Link href="/">{t.backHome}</Link>
        </p>
      </section>
    </main>
  );
}

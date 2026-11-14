import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Suspense } from "react";
import QuinteTopEight from "./quinte-top-eight";
import SiteNavigation from "./site-navigation";
import HomeAuthRedirect from "./home-auth-redirect";
import { fetchPublicTopEight } from "./race-data";
import { getRequestMessages } from "../i18n/server";
import { localeMeta } from "../i18n/config";

export const metadata: Metadata = {
  alternates: { canonical: "/" },
};

async function TopEightSection() {
  const initialAnalysis = await fetchPublicTopEight();
  return <QuinteTopEight initialAnalysis={initialAnalysis} />;
}

function quinteWidgetDocument(lang: string, offlineNote: string) {
  return `<!doctype html>
<html lang="${lang}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root { color-scheme: light; }
      * { box-sizing: border-box; }
      html, body { margin: 0; background: #fbfaf5; color: #18221f; font-family: Arial, sans-serif; }
      body { overflow-x: auto; }
      .widget-content { width: 100%; }
      .widget-fallback { margin: 0; padding: 1rem 1.25rem; border-left: 3px solid #c96f3b; background: #f3f0e8; color: #65736d; font: .85rem/1.5 Arial, sans-serif; }
      .widget-fallback[hidden] { display: none; }
      table.tableaux3 {
        width: 100% !important;
        border: 0 !important;
        border-collapse: separate;
        border-spacing: 0;
        background: #fbfaf5 !important;
        color: #18221f;
        font-family: Arial, sans-serif !important;
      }
      table.tableaux3 > tbody > tr > td { padding: 1.25rem !important; }
      table.tableaux3 h2 {
        margin: 0 0 .9rem;
        color: #103b32 !important;
        font: 700 1.2rem/1.35 Arial, sans-serif !important;
      }
      table.tableaux3 h2 a { color: #103b32 !important; text-decoration: none !important; }
      table.tableaux3 > tbody > tr > td > p:not(:empty) {
        margin: 0 0 1rem;
        padding: .75rem .9rem !important;
        border: 1px solid #d7d8ca;
        border-left: 3px solid #c96f3b;
        border-radius: .45rem;
        background: #f3f0e8 !important;
        color: #65736d;
        font:  .82rem/1.5 Arial, sans-serif !important;
      }
      table.inner-bloc {
        width: 100%;
        border: 1px solid #d7d8ca;
        border-collapse: separate;
        border-spacing: 0;
        border-radius: .5rem;
        overflow: hidden;
        background: #fbfaf5;
        font-family: Arial, sans-serif;
      }
      table.inner-bloc tr:first-child th {
        padding: .7rem .45rem !important;
        border-bottom: 1px solid #103b32;
        background: #103b32;
        color: #fff;
        text-align: left;
        white-space: nowrap;
        font: 700 .7rem/1.3 Arial, sans-serif !important;
      }
      table.inner-bloc tr:not(:first-child) td {
        padding: .65rem .45rem !important;
        border-bottom: 1px solid #e5e5dc;
        color: #18221f;
        font: .75rem/1.4 Arial, sans-serif !important;
        vertical-align: middle;
      }
      table.inner-bloc tr:nth-child(odd):not(:first-child) td { background: #f3f0e8; }
      table.inner-bloc tr:last-child td { border-bottom: 0; }
      table.inner-bloc tr:not(:first-child):hover td { background: #edf5ee; }
      table.inner-bloc td a { color: #1d594b !important; font-weight: 700; }
      table.inner-bloc td.casaque { width: 2.5rem; }
      table.inner-bloc td.casaque img { display: block; max-width: 25px; height: auto; }
      table.inner-bloc .origin { color: #65736d; }
      @media (max-width: 760px) {
        .widget-content, table.tableaux3, table.inner-bloc { min-width: 830px; }
      }
    </style>
  </head>
  <body>
    <div class="widget-content">
      <p class="widget-fallback" id="widget-fallback" hidden>${offlineNote}</p>
      <script>
        window.addEventListener("error", function () {
          var note = document.getElementById("widget-fallback");
          if (note) note.hidden = false;
        }, true);
      </script>
      <script src="/api/quinte-widget"></script>
    </div>
  </body>
</html>`;
}

function resultsWidgetDocument(widgetType: "results" | "live-results", lang: string, offlineNote: string) {
  return `<!doctype html>
<html lang="${lang}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      :root { color-scheme: light; }
      * { box-sizing: border-box; }
      html, body { margin: 0; background: #fbfaf5; color: #18221f; font-family: Arial, sans-serif; }
      .widget-content { width: 100%; }
      .widget-fallback { margin: 0; padding: 1rem 1.25rem; border-left: 3px solid #c96f3b; background: #f3f0e8; color: #65736d; font: .85rem/1.5 Arial, sans-serif; }
      .widget-fallback[hidden] { display: none; }
      table.tableaux3 {
        width: 100% !important;
        border: 0 !important;
        border-collapse: separate;
        border-spacing: 0;
        background: #fbfaf5 !important;
        font-family: Arial, sans-serif !important;
      }
      table.tableaux3 > tbody > tr > td { padding: .8rem !important; }
      table.tableaux3 strong:first-child {
        color: #103b32 !important;
        font: 700 .95rem/1.4 Arial, sans-serif !important;
      }
      table.tableaux3 strong:first-child a { color: #103b32 !important; text-decoration: none !important; }
      table.tableaux3 td > table {
        width: 100% !important;
        margin-top: .7rem !important;
        border: 1px solid #d7d8ca !important;
        border-collapse: separate;
        border-spacing: 0;
        border-radius: .45rem;
        overflow: hidden;
        background: #fbfaf5 !important;
      }
      table.tableaux3 td > table tr:nth-child(4n + 1) td,
      table.tableaux3 td > table tr:nth-child(4n + 2) td { background: #f3f0e8 !important; }
      table.tableaux3 td > table td {
        padding: .55rem .5rem !important;
        border: 0 !important;
        border-bottom: 1px solid #e5e5dc !important;
        color: #65736d !important;
        font: .75rem/1.5 Arial, sans-serif !important;
      }
      table.tableaux3 td > table tr:last-child td { border-bottom: 0 !important; }
      table.tableaux3 td > table a { color: #1d594b !important; }
      table.tableaux3 td > table a b,
      table.tableaux3 td > table strong { color: #103b32 !important; }
      ${widgetType === "live-results" ? `
      table.tableaux3 strong:first-child { font-size: .82rem !important; }
      table.tableaux3 td > table td,
      table.tableaux3 td > table td span,
      table.tableaux3 td > table td a,
      table.tableaux3 td > table td strong,
      table.tableaux3 td > table td em {
        font-size: .65rem !important;
        line-height: 1.35 !important;
      }
      table.tableaux3 td > table td { padding: .38rem .4rem !important; }
      ` : ""}
    </style>
  </head>
  <body>
    <div class="widget-content">
      <p class="widget-fallback" id="widget-fallback" hidden>${offlineNote}</p>
      <script>
        window.addEventListener("error", function () {
          var note = document.getElementById("widget-fallback");
          if (note) note.hidden = false;
        }, true);
      </script>
      <script src="/api/quinte-widget?type=${widgetType}"></script>
    </div>
  </body>
</html>`;
}

export default async function Home() {
  const { locale, messages } = await getRequestMessages();
  const t = messages.home;
  const lang = localeMeta[locale].htmlLang;

  return (
    <HomeAuthRedirect>
      <main className="public-home" lang={lang}>
      <header className="public-header">
        <Link className="public-brand" href="/" aria-label={t.brandAria}>
          <Image
            src="/racex-logo.png"
            alt="RaceX"
            width={540}
            height={180}
            priority
            className="public-logo"
          />
        </Link>
        <SiteNavigation currentPage="home" />
        <span className="public-edition">{t.edition}</span>
      </header>

      <section className="public-intro" aria-labelledby="quinte-title">
        <p className="public-kicker">{t.kicker}</p>
        <h1 id="quinte-title">{t.title}</h1>
        <p>{t.intro}</p>
      </section>

      <Suspense
        fallback={
          <section className="public-widget free-analysis" aria-labelledby="free-analysis-title" aria-live="polite">
            <div className="free-analysis-heading">
              <div>
                <p className="public-kicker">{messages.topEight.kicker}</p>
                <h2 id="free-analysis-title">{messages.topEight.title}</h2>
                <p className="free-analysis-description">{messages.topEight.description}</p>
              </div>
            </div>
            <p className="free-analysis-status" role="status">{messages.topEight.loading}</p>
          </section>
        }
      >
        <TopEightSection />
      </Suspense>

      <section className="quinte-dashboard" aria-label={t.dashboardAria}>
        <section className="public-widget starters-widget" aria-label={t.startersAria}>
          <iframe
            title={t.startersFrameTitle}
            srcDoc={quinteWidgetDocument(lang, t.widgetOffline)}
            sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
            className="quinte-widget-frame"
          />
        </section>

        <div className="quinte-sidebar">
          <aside className="public-widget results-widget" aria-label={t.resultsAria}>
            <h2 className="public-widget-heading">{t.resultsHeading}</h2>
            <iframe
              title={t.resultsFrameTitle}
              srcDoc={resultsWidgetDocument("results", lang, t.widgetOffline)}
              sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
              className="quinte-results-frame"
            />
          </aside>

          <aside className="public-widget live-results-widget" aria-label={t.liveResultsAria}>
            <h2 className="public-widget-heading">{t.liveResultsHeading}</h2>
            <iframe
              title={t.liveResultsFrameTitle}
              srcDoc={resultsWidgetDocument("live-results", lang, t.widgetOffline)}
              sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
              className="quinte-live-results-frame"
            />
          </aside>
        </div>
      </section>

      <footer className="public-footer">
        <p>
          {t.sourcePrefix}{" "}
          <a href="https://www.zone-turf.fr/quinte/" target="_blank" rel="noreferrer">
            Zone-Turf
          </a>
          . {t.sourceSuffix}
        </p>
      </footer>
      </main>
    </HomeAuthRedirect>
  );
}

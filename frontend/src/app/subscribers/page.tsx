"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import QuinteOddsChart from "../quinte-odds-chart";
import SiteNavigation from "../site-navigation";

type Horse = Record<string, string | number | boolean | null>;
type AnalysisSignal = { label: string; value: string; detail: string };
type AnalysisSection = { title: string; columns: string[]; rows: Horse[] };
type FlatOverview = {
  prognosis: Horse[];
  summary: Horse[];
  upset_potential: Horse[];
  consistency_score: Horse[];
  odds_divergence: Horse[];
  best_starting_posts: string[];
  track: string;
  distance: number;
  race_details: string;
};
type Analysis = {
  race_id: string;
  race_type: "flat" | "trot";
  row_count: number;
  rows: Horse[];
  race_details: string;
  model_version: string;
  prognosis: Horse[];
  signals: AnalysisSignal[];
  sections: AnalysisSection[];
  overview: FlatOverview;
  handicap: { distance: number | null; penalized_count: number } | null;
  model_predictions: { status: string; message: string | null } | null;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const numberFields = ["N°", "N", "Numero", "NUMERO", "NUM"];
const nameFields = ["CHEVAL", "Cheval", "NOM", "NAME"];
const scoreFields = ["Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score"];
const oddsFields = ["COTE", "Cote", "ODDS"];
const formFields = ["MUSIQUE", "DERNIÈRES PERF.", "FORME", "FORM"];

function firstValue(row: Horse, fields: string[]) {
  const field = fields.find((key) => row[key] !== null && row[key] !== undefined && row[key] !== "");
  return field ? String(row[field]) : "";
}

function scoreOf(row: Horse) {
  const raw = firstValue(row, scoreFields).trim().replace(",", ".");
  const score = Number(raw);
  return raw && Number.isFinite(score) ? score : null;
}

function displayScore(score: number | null) {
  return score === null ? "—" : score.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
}

function todayInParis() {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function raceDateLabel() {
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    dateStyle: "full",
  }).format(new Date());
}

function sectionRows(analysis: Analysis, title: string) {
  return analysis.sections.find((section) => section.title === title)?.rows ?? [];
}

function horseNumber(horse: Horse) {
  return firstValue(horse, numberFields) || "—";
}

function horseName(horse: Horse) {
  return firstValue(horse, nameFields) || "Cheval sans nom";
}

function horseMetric(horse: Horse, keys: string[]) {
  return firstValue(horse, keys) || "—";
}

function formatMetric(value: string) {
  const numeric = Number(value.replace(",", "."));
  return value && Number.isFinite(numeric)
    ? numeric.toLocaleString("fr-FR", { maximumFractionDigits: 2 })
    : value || "—";
}

function shoeingDescription(horse: Horse) {
  const rawEquipment = firstValue(horse, ["DEF.", "DEF", "Def"]);
  if (rawEquipment) return rawEquipment;

  const features = [
    ["Bare Front", "déferré antérieurs"],
    ["Bare Back", "déferré postérieurs"],
    ["Plate Front", "plaques antérieurs"],
    ["Plate Back", "plaques postérieurs"],
  ]
    .filter(([key]) => {
      const value = horse[key];
      return value === true || value === 1 || value === "1";
    })
    .map(([, label]) => label);
  if (features.length) return features.join(", ");

  const aggressiveness = firstValue(horse, ["Shoeing Aggressiveness"]);
  return aggressiveness ? `Indice ferrure ${aggressiveness}/4` : "Non renseignée";
}

function DisciplineHighlights({ analysis }: { analysis: Analysis }) {
  const isFlat = analysis.race_type === "flat";
  const flatCards = isFlat
    ? [
        {
          title: "Régularité des signaux",
          description: "Chevaux présents sur plusieurs critères favorables",
          rows: analysis.overview?.consistency_score ?? [],
          metricKeys: ["consistency_score", "Consistance"],
          metricLabel: "Facteurs",
        },
        {
          title: "Outsiders à surveiller",
          description: "Score composite mieux classé que la cote",
          rows: analysis.overview?.odds_divergence ?? analysis.overview?.upset_potential ?? [],
          metricKeys: ["Divergence", "divergence", "FinalUpset"],
          metricLabel: "Écart",
        },
      ]
    : [
        {
          title: "Prognosis trot",
          description: "Synthèse des signaux propres au trot",
          rows: sectionRows(analysis, "Summary & Prognosis"),
          metricKeys: ["Composite", "Status"],
          metricLabel: "Score",
        },
        {
          title: "Performance",
          description: "Coefficient de réussite, ajusté si handicap",
          rows: sectionRows(analysis, "Performance (S_COEFF)"),
          metricKeys: ["S_COEFF_Handicap_Adj", "S_COEFF_Handicap_Adjusted", "S_COEFF"],
          metricLabel: "S_COEFF",
        },
        {
          title: "Forme récente",
          description: "Tendance et moyenne des dernières performances",
          rows: sectionRows(analysis, "Form Trend"),
          metricKeys: ["Trend", "Recent_Avg"],
          metricLabel: "Tendance",
        },
        {
          title: "Risque de disqualification",
          description: "Échelle 0–100 : les valeurs élevées appellent à la prudence",
          rows: sectionRows(analysis, "Disqualification Risk"),
          metricKeys: ["DQ_Risk_Amplified", "DQ_Risk"],
          metricLabel: "Risque",
        },
      ];

  const fitnessRows = isFlat ? [] : sectionRows(analysis, "Fitness (FA/FM)").slice(0, 4);
  const shoeingRows = isFlat ? [] : sectionRows(analysis, "Shoeing Strategy").slice(0, 4);
  const bestPosts = analysis.overview?.best_starting_posts ?? [];
  const track = analysis.overview?.track ?? "";
  const distance = analysis.overview?.distance ?? 0;

  return (
    <section className="subscriber-discipline" aria-labelledby="subscriber-discipline-title">
      <div className="subscriber-section-heading">
        <div>
          <p className="public-kicker">FACTEURS PROPRES À LA DISCIPLINE</p>
          <h2 id="subscriber-discipline-title">{isFlat ? "Repères du plat" : "Repères du trot"}</h2>
          <p>
            {isFlat
              ? "Régularité, écart au marché et avantage des stalles lorsque ces données sont disponibles."
              : "Performance, forme, ferrure et risque de disqualification selon les données disponibles."}
          </p>
        </div>
      </div>
      <div className="subscriber-discipline-grid">
        {flatCards.map((card) => {
          const rows = card.rows.slice(0, 4);
          if (!rows.length) return null;
          return (
            <article className="subscriber-discipline-card" key={card.title}>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              <ol>
                {rows.map((horse, index) => (
                  <li key={`${horseNumber(horse)}-${index}`}>
                    <strong>{horseNumber(horse)}</strong>
                    <span>{horseName(horse)}</span>
                    <b>{formatMetric(horseMetric(horse, card.metricKeys))}</b>
                  </li>
                ))}
              </ol>
            </article>
          );
        })}
        {isFlat && bestPosts.length > 0 && (
          <article className="subscriber-discipline-card subscriber-posts-card">
            <h3>Stalles favorables</h3>
            <p>{track || "Hippodrome"}{distance ? ` · ${distance} m` : ""}</p>
            <div className="subscriber-posts-list" aria-label="Numéros associés aux stalles favorables">
              {bestPosts.map((number) => <span key={number}>{number}</span>)}
            </div>
          </article>
        )}
        {!isFlat && fitnessRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>Condition physique</h3>
            <p>Indice de forme : les valeurs les plus basses sont les meilleures.</p>
            <ol>
              {fitnessRows.map((horse, index) => (
                <li key={`${horseNumber(horse)}-${index}`}>
                  <strong>{horseNumber(horse)}</strong>
                  <span>{horseName(horse)}</span>
                  <b>{formatMetric(horseMetric(horse, ["Fitness_Adjusted", "Fitness"]))}</b>
                </li>
              ))}
            </ol>
          </article>
        )}
        {!isFlat && shoeingRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>Ferrure</h3>
            <p>Équipement déclaré pour la course, si renseigné.</p>
            <ol>
              {shoeingRows.map((horse, index) => {
                return (
                  <li key={`${horseNumber(horse)}-${index}`}>
                    <strong>{horseNumber(horse)}</strong>
                    <span>{horseName(horse)}</span>
                    <b>{shoeingDescription(horse)}</b>
                  </li>
                );
              })}
            </ol>
          </article>
        )}
      </div>
      {!isFlat && analysis.handicap && (
        <p className="subscriber-discipline-note">
          Handicap pris en compte : {analysis.handicap.penalized_count} partant(s) pénalisé(s)
          {analysis.handicap.distance ? ` · recul de ${analysis.handicap.distance} m` : ""}.
        </p>
      )}
    </section>
  );
}

function SubscriberDashboard() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadedAt, setLoadedAt] = useState("");

  const loadAnalysis = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: todayInParis() }),
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Impossible de charger l’analyse de la course.");
      }
      setAnalysis(payload as Analysis);
      setLoadedAt(new Intl.DateTimeFormat("fr-FR", {
        timeZone: "Europe/Paris",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date()));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Impossible de charger l’analyse de la course.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadAnalysis(), 0);
    return () => window.clearTimeout(initialLoad);
  }, [loadAnalysis]);

  function refreshAnalysis() {
    setLoading(true);
    setError("");
    void loadAnalysis();
  }

  const ranked = (analysis?.rows ?? [])
    .map((horse) => ({ horse, score: scoreOf(horse) }))
    .filter((item): item is { horse: Horse; score: number } => item.score !== null)
    .sort((first, second) => second.score - first.score);
  const contenders = ranked.slice(0, 8);
  const leadingHorse = contenders[0]?.horse;
  const leaderScore = contenders[0]?.score ?? null;
  const leaderOdds = leadingHorse ? firstValue(leadingHorse, oddsFields) : "";
  const leaderForm = leadingHorse ? firstValue(leadingHorse, formFields) : "";
  const lowestOdds = (analysis?.rows ?? [])
    .map((horse) => Number(firstValue(horse, oddsFields).trim().replace(",", ".")))
    .filter((odds) => Number.isFinite(odds) && odds > 0)
    .sort((first, second) => first - second)[0];
  const firstRunner = analysis?.rows[0];
  const venue = firstRunner ? firstValue(firstRunner, ["HIPPODROME", "HIPPO", "TRACK"]) : "";
  const distance = firstRunner ? firstValue(firstRunner, ["DIST.", "DISTANCE"]) : "";

  return (
    <main className="shell subscriber-shell">
      <SiteNavigation currentPage="subscribers" />
      <header className="subscriber-header">
        <div>
          <p className="subscriber-eyebrow">RACEX · ESPACE ABONNÉS</p>
          <h1>Votre tableau de bord Quinté+</h1>
          <p className="subscriber-date">{raceDateLabel()}</p>
        </div>
        <div className="subscriber-header-actions">
          {loadedAt && <span className="subscriber-updated">Données chargées à {loadedAt} · heure de Paris</span>}
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis} disabled={loading}>
            {loading ? "Actualisation…" : "Actualiser"}
          </button>
        </div>
      </header>

      {loading && <section className="subscriber-state" role="status">Chargement de l’analyse et des partants…</section>}
      {!loading && error && (
        <section className="subscriber-state subscriber-error" role="alert">
          <p>{error}</p>
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis}>Réessayer</button>
        </section>
      )}
      {!loading && !error && !analysis && <section className="subscriber-state">Aucune analyse n’est disponible pour le moment.</section>}

      {analysis && !loading && !error && (
        <>
          <section className="subscriber-race-summary" aria-label="Résumé de la course">
            <div><span>COURSE</span><strong>Quinté+ du jour</strong></div>
            {venue && <div><span>HIPPODROME</span><strong>{venue}</strong></div>}
            {distance && <div><span>DISTANCE</span><strong>{distance}</strong></div>}
            <div><span>PARTANTS ANALYSÉS</span><strong>{analysis.row_count}</strong></div>
            <div><span>DISCIPLINE</span><strong>{analysis.race_type === "flat" ? "Plat" : "Trot"}</strong></div>
          </section>

          {leadingHorse && (
            <section className="subscriber-featured public-widget" aria-labelledby="subscriber-pick-title">
              <div className="subscriber-featured-copy">
                <p className="public-kicker">POINT FORT DU MODÈLE</p>
                <h2 id="subscriber-pick-title">Meilleur score composite</h2>
                <p className="subscriber-featured-horse">
                  N° {firstValue(leadingHorse, numberFields) || "—"}{" "}
                  <strong>{firstValue(leadingHorse, nameFields) || "Cheval sans nom"}</strong>
                </p>
                <p className="subscriber-rationale">
                  Ce cheval arrive en tête du classement composite parmi les partants analysés.
                  {leaderScore !== null && <> Son score est de <strong>{displayScore(leaderScore)}</strong>.</>}
                  {leaderOdds && <> Cote relevée : <strong>{leaderOdds}</strong>.</>}
                  {leaderForm && <> Musique : <strong>{leaderForm}</strong>.</>}
                </p>
                <p className="subscriber-caveat">Classement indicatif fondé sur les données disponibles, sans garantie de résultat.</p>
              </div>
              <div className="subscriber-featured-stats">
                <div><span>SCORE COMPOSITE</span><strong>{displayScore(leaderScore)}</strong></div>
                <div><span>FAVORI DU MARCHÉ</span><strong>{lowestOdds === undefined ? "—" : lowestOdds.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}</strong></div>
                <div><span>CHEVAUX AU CLASSEMENT</span><strong>{contenders.length}</strong></div>
              </div>
            </section>
          )}

          <DisciplineHighlights analysis={analysis} />

          <section className="subscriber-contenders public-widget" aria-labelledby="subscriber-contenders-title">
            <div className="subscriber-section-heading">
              <div>
                <p className="public-kicker">SYNTHÈSE DES PARTANTS</p>
                <h2 id="subscriber-contenders-title">Les 8 principaux chevaux</h2>
                <p>Triés par score composite décroissant. Les cotes sont indicatives et peuvent évoluer.</p>
              </div>
              <Link href="/admin" className="subscriber-detail-link">Ouvrir l’analyse détaillée</Link>
            </div>
            {contenders.length > 0 ? (
              <ol className="subscriber-contender-list">
                {contenders.map(({ horse, score }, index) => (
                  <li key={`${firstValue(horse, numberFields)}-${index}`}>
                    <span className="subscriber-rank">{String(index + 1).padStart(2, "0")}</span>
                    <span className="subscriber-horse-number">{firstValue(horse, numberFields) || "—"}</span>
                    <span className="subscriber-horse-name">{firstValue(horse, nameFields) || "Cheval sans nom"}</span>
                    <span className="subscriber-score"><small>COMPOSITE</small><strong>{displayScore(score)}</strong></span>
                    <span className="subscriber-horse-odds"><small>COTE</small><strong>{firstValue(horse, oddsFields) || "—"}</strong></span>
                    <span className="subscriber-horse-form"><small>FORME</small><strong>{firstValue(horse, formFields) || "—"}</strong></span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="subscriber-state">Le score composite n’est pas disponible pour cette course.</p>
            )}
          </section>

          <QuinteOddsChart />

          <details className="subscriber-details public-widget">
            <summary>Comprendre les signaux et les limites de l’analyse</summary>
            {analysis.race_details && <p className="subscriber-race-details">{analysis.race_details}</p>}
            {analysis.signals.length > 0 && (
              <div className="subscriber-signals">
                {analysis.signals.map((signal) => (
                  <article key={signal.label}>
                    <span>{signal.label}</span><strong>{signal.value}</strong><p>{signal.detail}</p>
                  </article>
                ))}
              </div>
            )}
            <ul className="subscriber-methodology">
              <li>Le classement ci-dessus reflète le score composite disponible pour chaque partant.</li>
              <li>Les cotes sont des relevés périodiques, pas des données en temps réel.</li>
              <li>Les signaux peuvent être incomplets ou évoluer avant le départ.</li>
              {analysis.handicap && <li>Analyse handicap : {analysis.handicap.penalized_count} partant(s) pénalisé(s).</li>}
              {analysis.model_predictions?.message && <li>{analysis.model_predictions.message}</li>}
              <li>Version du modèle : {analysis.model_version}.</li>
            </ul>
          </details>
        </>
      )}
    </main>
  );
}

export default function SubscribersPage() {
  return <SubscriberDashboard />;
}

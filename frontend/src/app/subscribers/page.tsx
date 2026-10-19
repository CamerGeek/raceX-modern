"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import QuinteOddsChart from "../quinte-odds-chart";
import QuinteRecommendations, { type QuinteModelPredictions } from "../quinte-recommendations";
import SiteNavigation from "../site-navigation";
import AccessGate from "../access-gate";
import { useAuth } from "../auth-context";

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
  race_type: "flat" | "trot" | "obstacles";
  row_count: number;
  rows: Horse[];
  race_details: string;
  model_version: string;
  prognosis: Horse[];
  signals: AnalysisSignal[];
  sections: AnalysisSection[];
  overview: FlatOverview;
  handicap: { distance: number | null; penalized_count: number } | null;
  model_predictions: QuinteModelPredictions | null;
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

function raceDateLabel(value = todayInParis()) {
  return new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    dateStyle: "full",
  }).format(new Date(`${value}T12:00:00`));
}

function addDays(value: string, days: number) {
  const result = new Date(`${value}T00:00:00Z`);
  result.setUTCDate(result.getUTCDate() + days);
  return result.toISOString().slice(0, 10);
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

function horseNameWithoutParenthesizedContent(horse: Horse) {
  return horseName(horse).replace(/\s*\([^)]*\)/g, "").trim() || "Cheval sans nom";
}

function horseMetric(horse: Horse, keys: string[]) {
  return firstValue(horse, keys) || "—";
}

function lowestMetricFirst(rows: Horse[], keys: string[]) {
  return rows
    .map((horse, index) => {
      const rawMetric = firstValue(horse, keys).trim().replace(",", ".");
      const metric = rawMetric ? Number(rawMetric) : Number.NaN;
      return { horse, index, metric };
    })
    .filter((item): item is { horse: Horse; index: number; metric: number } =>
      Number.isFinite(item.metric),
    )
    .sort((first, second) => first.metric - second.metric || first.index - second.index)
    .map(({ horse }) => horse);
}

function formatMetric(value: string) {
  const numeric = Number(value.replace(",", "."));
  return value && Number.isFinite(numeric)
    ? numeric.toLocaleString("fr-FR", { maximumFractionDigits: 2 })
    : value || "—";
}

function DisciplineHighlights({ analysis }: { analysis: Analysis }) {
  const isFlat = analysis.race_type === "flat";
  const isTrot = analysis.race_type === "trot";
  const isObstacles = analysis.race_type === "obstacles";
  const disciplineCards = isFlat
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
    : isTrot
    ? [
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
          title: "Chevaux sûrs",
          description: "Classés du risque de disqualification le plus faible au plus élevé",
          rows: sectionRows(analysis, "Disqualification Risk"),
          metricKeys: ["DQ_Risk_Amplified", "DQ_Risk"],
          metricLabel: "Risque",
        },
      ]
    : [];

  const fitnessRows = isTrot ? sectionRows(analysis, "Fitness (FA/FM)").slice(0, 4) : [];
  const obstacleModelRows = isObstacles
    ? (analysis.model_predictions?.rows ?? [])
        .map((horse) => {
          const rawScore = firstValue(horse, ["place_prob_avg", "place_prob_deep", "place_prob"])
            .trim()
            .replace(",", ".");
          const score = rawScore ? Number(rawScore) : null;
          return { horse, score };
        })
        .filter((item): item is { horse: Horse; score: number } =>
          item.score !== null && Number.isFinite(item.score),
        )
        .sort((first, second) => second.score - first.score)
        .slice(0, 4)
    : [];
  const bestPosts = analysis.overview?.best_starting_posts ?? [];
  const track = analysis.overview?.track ?? "";
  const distance = analysis.overview?.distance ?? 0;

  return (
    <section className="subscriber-discipline" aria-labelledby="subscriber-discipline-title">
      <div className="subscriber-section-heading">
        <div>
          <p className="public-kicker">FACTEURS PROPRES À LA DISCIPLINE</p>
          <h2 id="subscriber-discipline-title">
            {isFlat ? "Repères du plat" : isTrot ? "Repères du trot" : "Repères des obstacles"}
          </h2>
          <p>
            {isFlat
              ? "Régularité, écart au marché et avantage des stalles lorsque ces données sont disponibles."
              : isTrot
              ? "Performance, forme et chevaux les moins exposés à la disqualification."
              : "Classement établi par les modèles dédiés aux courses d’obstacles."}
          </p>
        </div>
      </div>
      <div className="subscriber-discipline-grid">
        {disciplineCards.map((card) => {
          const orderedRows = card.title === "Chevaux sûrs"
            ? lowestMetricFirst(card.rows, card.metricKeys)
            : card.rows;
          const rows = orderedRows.slice(0, 4);
          if (!rows.length) return null;
          return (
            <article className="subscriber-discipline-card" key={card.title}>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              <ol>
                {rows.map((horse, index) => (
                  <li key={`${horseNumber(horse)}-${index}`}>
                    <strong>{horseNumber(horse)}</strong>
                    <span>
                      {card.title === "Forme récente"
                        ? horseNameWithoutParenthesizedContent(horse)
                        : horseName(horse)}
                    </span>
                    <b>{formatMetric(horseMetric(horse, card.metricKeys))}</b>
                  </li>
                ))}
              </ol>
            </article>
          );
        })}
        {isObstacles && obstacleModelRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>Classement du modèle obstacles</h3>
            <p>Scores de classement du modèle dédié, et non probabilités calibrées.</p>
            <ol>
              {obstacleModelRows.map(({ horse, score }, index) => (
                <li key={`${horseNumber(horse)}-${index}`}>
                  <strong>{horseNumber(horse)}</strong>
                  <span>{horseName(horse)}</span>
                  <b>{formatMetric(String(score))}</b>
                </li>
              ))}
            </ol>
          </article>
        )}
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
  const { apiFetch } = useAuth();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadedAt, setLoadedAt] = useState("");
  const [parisToday, setParisToday] = useState(todayInParis);
  const [selectedDayOffset, setSelectedDayOffset] = useState(0);
  const requestSequence = useRef(0);
  const selectedRaceDate = addDays(parisToday, selectedDayOffset);
  const selectedDayLabel = selectedDayOffset === -1
    ? "Quinté+ d'hier"
    : selectedDayOffset === 1
      ? "Quinté+ de demain"
      : "Quinté+ du jour";

  const loadAnalysis = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError("");
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: selectedRaceDate }),
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "Impossible de charger l’analyse de la course.");
      }
      if (sequence !== requestSequence.current) return;
      setAnalysis(payload as Analysis);
      setLoadedAt(new Intl.DateTimeFormat("fr-FR", {
        timeZone: "Europe/Paris",
        hour: "2-digit",
        minute: "2-digit",
      }).format(new Date()));
    } catch (loadError) {
      if (sequence !== requestSequence.current) return;
      setError(loadError instanceof Error ? loadError.message : "Impossible de charger l’analyse de la course.");
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [apiFetch, selectedRaceDate]);

  useEffect(() => {
    const updateParisDate = () => {
      const currentDate = todayInParis();
      setParisToday((previousDate) => previousDate === currentDate ? previousDate : currentDate);
    };
    const interval = window.setInterval(updateParisDate, 60_000);
    window.addEventListener("focus", updateParisDate);
    const initialLoad = window.setTimeout(() => void loadAnalysis(), 0);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
      window.removeEventListener("focus", updateParisDate);
    };
  }, [loadAnalysis]);

  function refreshAnalysis() {
    setLoading(true);
    setError("");
    void loadAnalysis();
  }

  function exportCurrentRacePdf() {
    const previousTitle = document.title;
    document.title = `RaceX-Quinte-${selectedRaceDate}`;
    window.addEventListener("afterprint", () => {
      document.title = previousTitle;
    }, { once: true });
    window.print();
  }

  const ranked = (analysis?.rows ?? [])
    .map((horse) => ({ horse, score: scoreOf(horse) }))
    .filter((item): item is { horse: Horse; score: number } => item.score !== null)
    .sort((first, second) => second.score - first.score);
  const completeCompositeScores = (analysis?.rows ?? [])
    .map((horse, index) => ({ horse, index, score: scoreOf(horse) }))
    .sort((first, second) => {
      if (first.score === null) return second.score === null ? first.index - second.index : 1;
      if (second.score === null) return -1;
      return second.score - first.score || first.index - second.index;
    });
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
          <p className="subscriber-date">{raceDateLabel(selectedRaceDate)}</p>
        </div>
        <div className="subscriber-header-actions">
          {loadedAt && <span className="subscriber-updated">Données chargées à {loadedAt} · heure de Paris</span>}
          {analysis && !loading && !error && (
            <button
              type="button"
              className="subscriber-refresh subscriber-export"
              onClick={exportCurrentRacePdf}
              title="Ouvre l’impression du navigateur pour enregistrer le document au format PDF."
            >
              Imprimer / enregistrer en PDF
            </button>
          )}
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis} disabled={loading}>
            {loading ? "Actualisation…" : "Actualiser"}
          </button>
        </div>
      </header>
      <div className="subscriber-race-date-switch" role="group" aria-label="Choisir la course à analyser">
        <button
          type="button"
          className={selectedDayOffset === -1 ? "selected" : ""}
          aria-pressed={selectedDayOffset === -1}
          onClick={() => setSelectedDayOffset(-1)}
        >
          Quinté+ d’hier
        </button>
        <button
          type="button"
          className={selectedDayOffset === 0 ? "selected" : ""}
          aria-pressed={selectedDayOffset === 0}
          onClick={() => setSelectedDayOffset(0)}
        >
          Quinté+ du jour
        </button>
        <button
          type="button"
          className={selectedDayOffset === 1 ? "selected" : ""}
          aria-pressed={selectedDayOffset === 1}
          onClick={() => setSelectedDayOffset(1)}
        >
          Quinté+ de demain
        </button>
      </div>

      {loading && <section className="subscriber-state" role="status">Chargement de l’analyse enregistrée…</section>}
      {!loading && error && (
        <section className="subscriber-state subscriber-error" role="alert">
          <p>{error}</p>
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis}>Réessayer</button>
        </section>
      )}
      {!loading && !error && !analysis && <section className="subscriber-state">Aucune analyse n’est disponible pour le moment.</section>}

      {analysis && !loading && !error && (
        <>
          <header className="subscriber-print-masthead">
            <div className="subscriber-print-brand">
              <svg
                aria-label="RaceX"
                role="img"
                viewBox="0 0 512 512"
                xmlns="http://www.w3.org/2000/svg"
              >
                <rect width="512" height="512" rx="112" fill="#103b32" />
                <path d="M75 105h362v58H303L124 349h142v58H75v-58l179-186H75z" fill="#f3f0e8" />
                <path d="M310 224 437 407h-75l-90-130-91 130h-72l127-181-112-161h75l75 108 76-108h72z" fill="#2ac7ff" />
              </svg>
              <div>
                <p className="subscriber-eyebrow">RACEX · {selectedDayLabel.toLocaleUpperCase("fr-FR")}</p>
                <h1>Le journal des courses</h1>
                <p>
                  {raceDateLabel(selectedRaceDate)}
                  {venue && <> · {venue}</>}
                  {distance && <> · {distance}</>}
                  {" · "}
                  {analysis.race_type === "flat" ? "Plat" : analysis.race_type === "obstacles" ? "Obstacles" : "Trot"}
                </p>
              </div>
            </div>
            <span>Analyse chargée à {loadedAt} · heure de Paris · Modèle {analysis.model_version}</span>
          </header>

          <section className="subscriber-race-summary" aria-label="Résumé de la course">
            <div><span>COURSE</span><strong>{selectedDayLabel}</strong></div>
            {venue && <div><span>HIPPODROME</span><strong>{venue}</strong></div>}
            {distance && <div><span>DISTANCE</span><strong>{distance}</strong></div>}
            <div><span>PARTANTS ANALYSÉS</span><strong>{analysis.row_count}</strong></div>
            <div><span>DISCIPLINE</span><strong>{analysis.race_type === "flat" ? "Plat" : analysis.race_type === "obstacles" ? "Obstacles" : "Trot"}</strong></div>
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

          <QuinteRecommendations
            prognosis={analysis.prognosis}
            modelPredictions={analysis.model_predictions}
          />

          <section className="subscriber-composite-scores public-widget" aria-labelledby="subscriber-composite-scores-title">
            <div className="subscriber-section-heading">
              <div>
                <p className="public-kicker">CLASSEMENT COMPLET</p>
                <h2 id="subscriber-composite-scores-title">Scores composites de tous les partants</h2>
                <p>Classés du score composite le plus élevé au plus faible.</p>
              </div>
            </div>
            <div className="subscriber-composite-table-wrap">
              <table className="subscriber-composite-table">
                <thead>
                  <tr>
                    <th scope="col">Rang</th>
                    <th scope="col">N°</th>
                    <th scope="col">Cheval</th>
                    <th scope="col">Cote</th>
                    <th scope="col">Forme récente</th>
                    <th scope="col">Score composite</th>
                  </tr>
                </thead>
                <tbody>
                  {completeCompositeScores.map(({ horse, index, score }, rank) => (
                    <tr key={`${horseNumber(horse)}-${index}`}>
                      <td>{score === null ? "—" : rank + 1}</td>
                      <td>{horseNumber(horse)}</td>
                      <td>{horseName(horse)}</td>
                      <td>{firstValue(horse, oddsFields) || "—"}</td>
                      <td>{firstValue(horse, formFields) || "—"}</td>
                      <td>{displayScore(score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <DisciplineHighlights analysis={analysis} />

          <footer className="subscriber-print-footer">
            <p>
              Analyse indicative fondée sur les données disponibles au moment du chargement. Les scores,
              pronostics et cotes peuvent évoluer et ne garantissent aucun résultat ; ce document ne
              constitue pas un conseil de mise.
            </p>
            <span>
              © {new Date().getFullYear()} RaceX · Développé par Georges BODIONG
              <br />
              deebodiong@gmail.com · +22660354400 / +22674911538
            </span>
          </footer>

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
              <li><strong>Pronostic (Prono Flash) :</strong> en plat et en obstacles, il croise les classements de forme (IF), de classe (IC) et de coefficient de réussite (S_COEFF). Les chevaux présents dans la moitié supérieure des trois classements sont prioritaires, puis ceux présents dans deux ; ceux repérés dans un seul peuvent compléter la sélection jusqu’à huit. Au trot, il combine sept indicateurs pondérés : coefficient de réussite (20 %), forme/fitness (15 %), tendance (15 %), risque de disqualification (20 %), cote (15 %), courses récentes (10 %) et ferrure (5 %). Chaque indicateur disponible contribue pour les chevaux figurant dans sa moitié supérieure.</li>
              <li><strong>Model Shortlist :</strong> classement distinct du Pronostic, établi en triant les chevaux par score Deep décroissant, jusqu’à huit partants. Les scores servent à classer ; ils ne sont pas des probabilités de victoire ou de placé calibrées.</li>
              <li><strong>Votes et Consensus des votes :</strong> les votes ne viennent pas des utilisateurs, mais de sources de modèles. Un cheval reçoit un vote s’il figure parmi les trois meilleurs scores de placé, les trois meilleurs scores de victoire, les quatre meilleurs scores « dark horse » ou, si disponible, les trois meilleurs scores Deep. En plat, les pronostics présents dans les données peuvent aussi compter comme une source. Le Consensus classe tous les chevaux ayant au moins un vote, du plus grand nombre au plus petit ; il s’agit d’un signal distinct du Pronostic et du Model Shortlist.</li>
              <li>Les cotes sont des relevés périodiques, pas des données en temps réel.</li>
              <li>Les signaux peuvent être incomplets ou évoluer avant le départ.</li>
              {analysis.handicap && <li>Analyse handicap : {analysis.handicap.penalized_count} partant(s) pénalisé(s).</li>}
              {analysis.model_predictions?.message && <li>{analysis.model_predictions.message}</li>}
              <li>Version du modèle : {analysis.model_version}.</li>
            </ul>
          </details>
        </>
      )}
      <QuinteOddsChart meetingDate={selectedRaceDate} />
    </main>
  );
}

export default function SubscribersPage() {
  return <AccessGate allowedRoles={["demo", "subscriber", "admin"]}><SubscriberDashboard /></AccessGate>;
}

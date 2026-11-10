"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import QuinteOddsChart from "../quinte-odds-chart";
import QuinteRecommendations, {
  getModelShortlistRows,
  getModelWinRows,
  ReadyTicketsGrid,
  ShodHorsesCard,
  winScoreOf,
  type PlotTwistItem,
  type QuinteModelPredictions,
  type ReadyTicket,
} from "../quinte-recommendations";
import SiteNavigation from "../site-navigation";
import AccessGate from "../access-gate";
import CombinationsPanel from "./combinations-panel";
import { useAuth } from "../auth-context";
import { offlineKeys, readOffline, saveOffline } from "../offline-data";
import { useOnlineStatus } from "../use-online-status";
import { interpolate } from "../../i18n/format";
import { useI18n } from "../../i18n/provider";

type Horse = Record<string, string | number | boolean | null>;
type AnalysisSignal = { label: string; value: string; detail: string };
type AnalysisSection = { title: string; columns: string[]; rows: Horse[] };
type FlatOverview = {
  prognosis?: Horse[];
  summary?: Horse[];
  upset_potential?: Horse[];
  consistency_score?: Horse[];
  odds_divergence?: Horse[];
  best_starting_posts?: string[];
  track?: string;
  distance?: number;
  race_details?: string;
};
type Analysis = {
  race_id: string;
  race_type: "flat" | "trot" | "obstacles";
  row_count: number;
  rows: Horse[];
  non_partant_numbers: string[];
  expert_commentary: string | null;
  race_details: string;
  model_version: string;
  prognosis: Horse[];
  signals: AnalysisSignal[];
  sections: AnalysisSection[];
  overview: FlatOverview;
  handicap: { distance: number | null; penalized_count: number } | null;
  model_predictions: QuinteModelPredictions | null;
  ready_tickets?: ReadyTicket[];
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

function plotTwistCandidates(rows: Horse[]): PlotTwistItem[] {
  const rankedRows = rows
    .map((horse, index) => ({ horse, index, score: scoreOf(horse) }))
    .filter((item): item is { horse: Horse; index: number; score: number } =>
      item.score !== null,
    )
    .sort((first, second) => second.score - first.score || first.index - second.index);
  if (rankedRows.length <= 8) return [];

  const scores = rankedRows.map(({ score }) => score);
  const mean = scores.reduce((sum, score) => sum + score, 0) / scores.length;
  const middle = Math.floor(scores.length / 2);
  const median = scores.length % 2 === 0
    ? (scores[middle - 1] + scores[middle]) / 2
    : scores[middle];

  return rankedRows
    .map((item, index) => ({
      ...item,
      rank: index + 1,
      nearMean: Math.abs(item.score - mean) <= 0.05,
      nearMedian: Math.abs(item.score - median) <= 0.05,
    }))
    .filter((item) => item.rank > 8 && (item.nearMean || item.nearMedian))
    .slice(0, 4);
}

function displayScore(score: number | null, intlLocale: string) {
  return score === null ? "—" : score.toLocaleString(intlLocale, { maximumFractionDigits: 2 });
}

function todayInParis() {
  return new Intl.DateTimeFormat("fr-CA", {
    timeZone: "Europe/Paris",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function raceDateLabel(value: string, intlLocale: string) {
  return new Intl.DateTimeFormat(intlLocale, {
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

function horseName(horse: Horse, fallback: string) {
  return firstValue(horse, nameFields) || fallback;
}

function horseNameWithoutParenthesizedContent(horse: Horse, fallback: string) {
  return horseName(horse, fallback).replace(/\s*\([^)]*\)/g, "").trim() || fallback;
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

function formatMetric(value: string, intlLocale: string) {
  const numeric = Number(value.replace(",", "."));
  return value && Number.isFinite(numeric)
    ? numeric.toLocaleString(intlLocale, { maximumFractionDigits: 2 })
    : value || "—";
}

function DisciplineHighlights({ analysis }: { analysis: Analysis }) {
  const { messages, intlLocale } = useI18n();
  const t = messages.subscribers;
  const d = t.discipline;
  const isFlat = analysis.race_type === "flat";
  const isTrot = analysis.race_type === "trot";
  const isObstacles = analysis.race_type === "obstacles";
  const unknownHorse = messages.recommendations.unknownHorse;

  const disciplineCards = isFlat || isObstacles
    ? [
        {
          id: "consistency",
          title: d.consistencyTitle,
          description: d.consistencyDescription,
          rows: analysis.overview?.consistency_score ?? [],
          metricKeys: ["consistency_score", "Consistance"],
          metricLabel: d.consistencyMetric,
        },
        {
          id: "upsets",
          title: d.upsetsTitle,
          description: d.upsetsDescription,
          rows: analysis.overview?.odds_divergence ?? analysis.overview?.upset_potential ?? [],
          metricKeys: ["Divergence", "divergence", "FinalUpset"],
          metricLabel: d.upsetsMetric,
        },
      ]
    : isTrot
    ? [
        {
          id: "performance",
          title: d.performanceTitle,
          description: d.performanceDescription,
          rows: sectionRows(analysis, "Performance (S_COEFF)"),
          metricKeys: ["S_COEFF_Handicap_Adj", "S_COEFF_Handicap_Adjusted", "S_COEFF"],
          metricLabel: "S_COEFF",
        },
        {
          id: "form",
          title: d.formTitle,
          description: d.formDescription,
          rows: sectionRows(analysis, "Form Trend"),
          metricKeys: ["Trend", "Recent_Avg"],
          metricLabel: d.formMetric,
        },
        {
          id: "safe",
          title: d.safeTitle,
          description: d.safeDescription,
          rows: sectionRows(analysis, "Disqualification Risk"),
          metricKeys: ["DQ_Risk_Amplified", "DQ_Risk"],
          metricLabel: d.safeMetric,
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
  const obstacleFormRows = isObstacles
    ? (analysis.model_predictions?.rows ?? [])
        .map((horse, index) => {
          const rawScore = firstValue(horse, ["FORM_DISCIPLINE"]).trim().replace(",", ".");
          const score = rawScore ? Number(rawScore) : null;
          const rawSuccess = firstValue(horse, ["S_COEFF"]).trim().replace(",", ".");
          const success = rawSuccess ? Number(rawSuccess) : null;
          return { horse, index, score, success };
        })
        .filter((item): item is { horse: Horse; index: number; score: number; success: number | null } =>
          item.score !== null && Number.isFinite(item.score),
        )
        .sort((first, second) => first.score - second.score || first.index - second.index)
        .slice(0, 4)
    : [];
  const obstacleDisciplineCode = firstValue(analysis.model_predictions?.rows[0] ?? {}, ["DISCIPLINE"]);
  const obstacleDisciplineLabel = ({
    h: d.disciplineHaies,
    s: d.disciplineSteeple,
    c: d.disciplineCross,
  } as Record<string, string>)[obstacleDisciplineCode] ?? d.disciplineObstacles;
  const obstacleIncidentRows = isObstacles
    ? (analysis.model_predictions?.rows ?? [])
        .map((horse, index) => ({
          horse,
          index,
          falls: Number(firstValue(horse, ["FALL_COUNT"])) || 0,
          stops: Number(firstValue(horse, ["STOP_COUNT"])) || 0,
        }))
        .filter(({ falls, stops }) => falls > 0 || stops > 0)
        .sort((first, second) =>
          second.stops - first.stops
          || second.falls - first.falls
          || first.index - second.index,
        )
        .slice(0, 4)
    : [];
  const obstacleMusicAvailable = isObstacles
    && (analysis.model_predictions?.rows ?? []).some(
      (horse) => Number(firstValue(horse, ["MUSIC_AVAILABLE"])) > 0,
    );
  const bestPosts = analysis.overview?.best_starting_posts ?? [];
  const track = analysis.overview?.track ?? "";
  const distance = analysis.overview?.distance ?? 0;

  return (
    <section className="subscriber-discipline" aria-labelledby="subscriber-discipline-title">
      <div className="subscriber-section-heading">
        <div>
          <p className="public-kicker">{d.kicker}</p>
          <h2 id="subscriber-discipline-title">
            {isFlat ? d.titleFlat : isTrot ? d.titleTrot : d.titleObstacles}
          </h2>
          <p>
            {isFlat ? d.introFlat : isTrot ? d.introTrot : d.introObstacles}
          </p>
        </div>
      </div>
      <div className="subscriber-discipline-grid">
        {disciplineCards.map((card) => {
          const orderedRows = card.id === "safe"
            ? lowestMetricFirst(card.rows, card.metricKeys)
            : card.rows;
          const rows = orderedRows.slice(0, 4);
          if (!rows.length) return null;
          return (
            <article className="subscriber-discipline-card" key={card.id}>
              <h3>{card.title}</h3>
              <p>{card.description}</p>
              <ol>
                {rows.map((horse, index) => (
                  <li key={`${horseNumber(horse)}-${index}`}>
                    <strong>{horseNumber(horse)}</strong>
                    <span>
                      {card.id === "form"
                        ? horseNameWithoutParenthesizedContent(horse, unknownHorse)
                        : horseName(horse, unknownHorse)}
                    </span>
                    <b>{formatMetric(horseMetric(horse, card.metricKeys), intlLocale)}</b>
                  </li>
                ))}
              </ol>
            </article>
          );
        })}
        {isObstacles && obstacleModelRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>{d.obstacleModelTitle}</h3>
            <p>{d.obstacleModelDescription}</p>
            <ol>
              {obstacleModelRows.map(({ horse, score }, index) => (
                <li key={`${horseNumber(horse)}-${index}`}>
                  <strong>{horseNumber(horse)}</strong>
                  <span>{horseName(horse, unknownHorse)}</span>
                  <b>{formatMetric(String(score), intlLocale)}</b>
                </li>
              ))}
            </ol>
          </article>
        )}
        {isObstacles && obstacleFormRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>{interpolate(d.obstacleFormTitle, { discipline: obstacleDisciplineLabel })}</h3>
            <p>{d.obstacleFormDescription}</p>
            <ol>
              {obstacleFormRows.map(({ horse, score, success }, index) => (
                <li key={`obstacle-form-${horseNumber(horse)}-${index}`}>
                  <strong>{horseNumber(horse)}</strong>
                  <span>{horseName(horse, unknownHorse)}</span>
                  <b>
                    {formatMetric(String(score), intlLocale)}
                    {success !== null && Number.isFinite(success)
                      ? interpolate(d.obstacleSuccess, { value: formatMetric(String(success), intlLocale) })
                      : ""}
                  </b>
                </li>
              ))}
            </ol>
          </article>
        )}
        {isObstacles && obstacleMusicAvailable && (
          <article className="subscriber-discipline-card">
            <h3>{d.incidentsTitle}</h3>
            <p>{d.incidentsDescription}</p>
            {obstacleIncidentRows.length > 0 ? (
              <ol>
                {obstacleIncidentRows.map(({ horse, falls, stops }, index) => {
                  return (
                    <li key={`obstacle-incident-${horseNumber(horse)}-${index}`}>
                      <strong>{horseNumber(horse)}</strong>
                      <span>{horseName(horse, unknownHorse)}</span>
                      <b>{interpolate(d.incidentsCount, { stops, falls })}</b>
                    </li>
                  );
                })}
              </ol>
            ) : (
              <p className="free-analysis-status">{d.incidentsNone}</p>
            )}
          </article>
        )}
        {isFlat && bestPosts.length > 0 && (
          <article className="subscriber-discipline-card subscriber-posts-card">
            <h3>{d.postsTitle}</h3>
            <p>{track || d.trackFallback}{distance ? ` · ${distance} m` : ""}</p>
            <div className="subscriber-posts-list" aria-label={d.postsAria}>
              {bestPosts.map((number) => <span key={number}>{number}</span>)}
            </div>
          </article>
        )}
        {!isFlat && fitnessRows.length > 0 && (
          <article className="subscriber-discipline-card">
            <h3>{d.fitnessTitle}</h3>
            <p>{d.fitnessDescription}</p>
            <ol>
              {fitnessRows.map((horse, index) => (
                <li key={`${horseNumber(horse)}-${index}`}>
                  <strong>{horseNumber(horse)}</strong>
                  <span>{horseName(horse, unknownHorse)}</span>
                  <b>{formatMetric(horseMetric(horse, ["Fitness_Adjusted", "Fitness"]), intlLocale)}</b>
                </li>
              ))}
            </ol>
          </article>
        )}
      </div>
      {!isFlat && analysis.handicap && (
        <p className="subscriber-discipline-note">
          {interpolate(d.handicapNote, {
            count: analysis.handicap.penalized_count,
            distance: analysis.handicap.distance
              ? interpolate(d.handicapDistance, { distance: analysis.handicap.distance })
              : "",
          })}
        </p>
      )}
    </section>
  );
}

function SubscriberDashboard() {
  const { apiFetch, profile: accountProfile, session } = useAuth();
  const { messages, intlLocale, locale } = useI18n();
  const t = messages.subscribers;
  const online = useOnlineStatus();
  const userId = session?.user.id ?? accountProfile?.id ?? null;
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadedAt, setLoadedAt] = useState("");
  const [cachedAt, setCachedAt] = useState<number | null>(null);
  const [parisToday, setParisToday] = useState(todayInParis);
  const [selectedDayOffset, setSelectedDayOffset] = useState(0);
  const [dashboardTab, setDashboardTab] = useState<"analysis" | "combinations">("analysis");
  const requestSequence = useRef(0);
  const wasOnline = useRef(online);
  const selectedRaceDate = addDays(parisToday, selectedDayOffset);
  const selectedDayLabel = selectedDayOffset === -1
    ? t.dayYesterday
    : selectedDayOffset === 1
      ? t.dayTomorrow
      : t.dayToday;

  const loadAnalysis = useCallback(async () => {
    const sequence = ++requestSequence.current;
    setLoading(true);
    setError("");
    const cacheKey = userId ? offlineKeys.analysis(userId, selectedRaceDate) : null;
    const timeFormat = new Intl.DateTimeFormat(intlLocale, {
      timeZone: "Europe/Paris",
      hour: "2-digit",
      minute: "2-digit",
    });
    const applyCached = async () => {
      const cached = cacheKey ? await readOffline<Analysis>(cacheKey) : null;
      if (sequence !== requestSequence.current) return false;
      if (!cached) return false;
      setAnalysis(cached.payload);
      setCachedAt(cached.savedAt);
      setLoadedAt(timeFormat.format(new Date(cached.savedAt)));
      return true;
    };
    if (!online || !userId) {
      if (!(await applyCached())) {
        if (sequence === requestSequence.current) setError(t.loadError);
      }
      if (sequence === requestSequence.current) setLoading(false);
      return;
    }
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: selectedRaceDate, locale }),
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail ?? "");
      }
      if (sequence !== requestSequence.current) return;
      setAnalysis(payload as Analysis);
      setCachedAt(null);
      setLoadedAt(timeFormat.format(new Date()));
      if (cacheKey) void saveOffline(cacheKey, payload as Analysis);
    } catch (loadError) {
      if (sequence !== requestSequence.current) return;
      if (!(await applyCached())) {
        setError(loadError instanceof Error && loadError.message ? loadError.message : t.loadError);
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [apiFetch, online, selectedRaceDate, intlLocale, locale, t.loadError, userId]);

  useEffect(() => {
    if (online && !wasOnline.current) void loadAnalysis();
    wasOnline.current = online;
  }, [online, loadAnalysis]);

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

  const completeCompositeScores = (analysis?.rows ?? [])
    .map((horse, index) => ({ horse, index, score: scoreOf(horse) }))
    .sort((first, second) => {
      if (first.score === null) return second.score === null ? first.index - second.index : 1;
      if (second.score === null) return -1;
      return second.score - first.score || first.index - second.index;
    });
  const plotTwistRows = analysis ? plotTwistCandidates(analysis.rows) : [];
  const modelShortlistRows = getModelShortlistRows(analysis?.model_predictions ?? null);
  const readyTickets = analysis?.ready_tickets ?? [];
  const leadingHorse = getModelWinRows(analysis?.model_predictions ?? null)[0];
  const leaderScoreText = leadingHorse ? winScoreOf(leadingHorse) : "";
  const leaderScoreValue = Number(leaderScoreText.trim().replace(",", "."));
  const leaderScore = leaderScoreText && Number.isFinite(leaderScoreValue) ? leaderScoreValue : null;
  const leaderOdds = leadingHorse ? firstValue(leadingHorse, oddsFields) : "";
  const leaderForm = leadingHorse ? firstValue(leadingHorse, formFields) : "";
  const lowestOdds = (analysis?.rows ?? [])
    .map((horse) => Number(firstValue(horse, oddsFields).trim().replace(",", ".")))
    .filter((odds) => Number.isFinite(odds) && odds > 0)
    .sort((first, second) => first - second)[0];
  const firstRunner = analysis?.rows[0];
  const venue = firstRunner ? firstValue(firstRunner, ["HIPPODROME", "HIPPO", "TRACK"]) : "";
  const distance = firstRunner ? firstValue(firstRunner, ["DIST.", "DISTANCE"]) : "";
  const disciplineLabel = analysis
    ? analysis.race_type === "flat"
      ? t.disciplines.flat
      : analysis.race_type === "obstacles"
        ? t.disciplines.obstacles
        : t.disciplines.trot
    : "";
  const unknownHorse = messages.recommendations.unknownHorse;

  return (
    <main className="shell subscriber-shell">
      <SiteNavigation currentPage="subscribers" />
      <header className="subscriber-header">
        <div>
          <p className="subscriber-eyebrow">{t.eyebrow}</p>
          <h1>{t.title}</h1>
          <p className="subscriber-date">{raceDateLabel(selectedRaceDate, intlLocale)}</p>
        </div>
        <div className="subscriber-header-actions">
          {loadedAt && <span className="subscriber-updated">{interpolate(t.loadedAt, { time: loadedAt })}</span>}
          {analysis && !loading && !error && dashboardTab === "analysis" && (
            <button
              type="button"
              className="subscriber-refresh subscriber-export"
              onClick={exportCurrentRacePdf}
              title={t.printTooltip}
            >
              {t.printCta}
            </button>
          )}
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis} disabled={loading}>
            {loading ? t.refreshing : t.refresh}
          </button>
        </div>
      </header>
      <div className="subscriber-race-date-switch" role="group" aria-label={t.dateSwitchAria}>
        <button
          type="button"
          className={selectedDayOffset === -1 ? "selected" : ""}
          aria-pressed={selectedDayOffset === -1}
          onClick={() => setSelectedDayOffset(-1)}
        >
          {t.dayYesterday}
        </button>
        <button
          type="button"
          className={selectedDayOffset === 0 ? "selected" : ""}
          aria-pressed={selectedDayOffset === 0}
          onClick={() => setSelectedDayOffset(0)}
        >
          {t.dayToday}
        </button>
        <button
          type="button"
          className={selectedDayOffset === 1 ? "selected" : ""}
          aria-pressed={selectedDayOffset === 1}
          onClick={() => setSelectedDayOffset(1)}
        >
          {t.dayTomorrow}
        </button>
      </div>
      {selectedDayOffset === 0 && (
        <p className="subscriber-analysis-notice">{t.notice}</p>
      )}

      {analysis && !error && (
        <div className="report-tabs subscriber-report-tabs" role="tablist" aria-label={t.combinations.tabsAria}>
          <button
            type="button"
            role="tab"
            className={dashboardTab === "analysis" ? "active" : ""}
            aria-selected={dashboardTab === "analysis"}
            onClick={() => setDashboardTab("analysis")}
          >
            {t.combinations.tabAnalysis}
          </button>
          <button
            type="button"
            role="tab"
            className={dashboardTab === "combinations" ? "active" : ""}
            aria-selected={dashboardTab === "combinations"}
            onClick={() => setDashboardTab("combinations")}
          >
            {t.combinations.tabCombinations}
          </button>
        </div>
      )}

      {analysis && (cachedAt !== null || !online) && (
        <p className="subscriber-offline-banner" role="status">
          {cachedAt !== null
            ? interpolate(t.offlineBanner, {
                time: new Intl.DateTimeFormat(intlLocale, {
                  timeZone: "Europe/Paris",
                  hour: "2-digit",
                  minute: "2-digit",
                }).format(new Date(cachedAt)),
              })
            : messages.cache.fromDevice}
        </p>
      )}

      {loading && <section className="subscriber-state" role="status">{t.loading}</section>}
      {!loading && error && (
        <section className="subscriber-state subscriber-error" role="alert">
          <p>{error}</p>
          <button type="button" className="subscriber-refresh" onClick={refreshAnalysis}>{t.retry}</button>
        </section>
      )}
      {!loading && !error && !analysis && <section className="subscriber-state">{t.empty}</section>}

      {analysis && !loading && !error && dashboardTab === "analysis" && (
        <>
          <header className="subscriber-print-masthead">
            <div className="subscriber-print-brand">
              <Image
                src="/icons/icon-96.png"
                alt="RaceX"
                width={96}
                height={96}
                priority
                className="subscriber-print-logo"
              />
              <div>
                <p className="subscriber-eyebrow">{interpolate(t.printEyebrow, { day: selectedDayLabel.toLocaleUpperCase(intlLocale) })}</p>
                <h1>{t.printTitle}</h1>
                <p>
                  {raceDateLabel(selectedRaceDate, intlLocale)}
                  {venue && <> · {venue}</>}
                  {distance && <> · {distance}</>}
                  {" · "}
                  {disciplineLabel}
                </p>
              </div>
            </div>
            <span>{interpolate(t.printLoadedAt, { time: loadedAt, model: analysis.model_version })}</span>
          </header>

          <section className="subscriber-race-summary" aria-label={t.summaryAria}>
            <div><span>{t.summary.race}</span><strong>{selectedDayLabel}</strong></div>
            {venue && <div><span>{t.summary.venue}</span><strong>{venue}</strong></div>}
            {distance && <div><span>{t.summary.distance}</span><strong>{distance}</strong></div>}
            <div><span>{t.summary.runners}</span><strong>{analysis.row_count}</strong></div>
            <div><span>{t.summary.discipline}</span><strong>{disciplineLabel}</strong></div>
          </section>

          <div className="subscriber-status-grid">
            <section className="subscriber-non-partants public-widget" aria-labelledby="subscriber-non-partants-title">
              <div>
                <p className="public-kicker">{t.nonPartants.kicker}</p>
                <h2 id="subscriber-non-partants-title">{t.nonPartants.title}</h2>
              </div>
              {analysis.non_partant_numbers.length > 0 ? (
                <ul aria-label={t.nonPartants.listAria}>
                  {analysis.non_partant_numbers.map((number) => <li key={number}>{number}</li>)}
                </ul>
              ) : (
                <p>{t.nonPartants.none}</p>
              )}
            </section>
            {analysis.race_type === "trot" && <ShodHorsesCard rows={analysis.rows} />}
          </div>

          {leadingHorse && (
            <section className="subscriber-featured public-widget" aria-labelledby="subscriber-pick-title">
              <div className="subscriber-featured-copy">
                <p className="public-kicker">{t.featured.kicker}</p>
                <h2 id="subscriber-pick-title">{t.featured.title}</h2>
                <p className="subscriber-featured-horse">
                  {interpolate(t.featured.horse, {
                    number: firstValue(leadingHorse, numberFields) || "—",
                    name: firstValue(leadingHorse, nameFields) || unknownHorse,
                  })}
                </p>
                <p className="subscriber-rationale">
                  {t.featured.rationale}
                  {leaderScore !== null && <> {interpolate(t.featured.rationaleScore, { score: displayScore(leaderScore, intlLocale) })}</>}
                  {leaderOdds && <> {interpolate(t.featured.rationaleOdds, { odds: leaderOdds })}</>}
                  {leaderForm && <> {interpolate(t.featured.rationaleForm, { form: leaderForm })}</>}
                </p>
                <p className="subscriber-caveat">{t.featured.caveat}</p>
              </div>
              <div className="subscriber-featured-stats">
                <div><span>{t.featured.winScore}</span><strong>{displayScore(leaderScore, intlLocale)}</strong></div>
                <div><span>{t.featured.marketFav}</span><strong>{lowestOdds === undefined ? "—" : lowestOdds.toLocaleString(intlLocale, { maximumFractionDigits: 2 })}</strong></div>
                <div><span>{t.featured.shortlisted}</span><strong>{modelShortlistRows.length}</strong></div>
              </div>
            </section>
          )}

          <QuinteRecommendations
            modelPredictions={analysis.model_predictions}
            plotTwistRows={plotTwistRows}
          />

          {readyTickets.length > 0 && (
            <section className="subscriber-ready-tickets public-widget" aria-labelledby="subscriber-ready-tickets-title">
              <div className="ready-tickets">
                <h4 id="subscriber-ready-tickets-title">{t.combinations.readyTitle}</h4>
                <ReadyTicketsGrid tickets={readyTickets} labels={t.combinations} />
              </div>
            </section>
          )}

          {analysis.expert_commentary && (
            <section className="subscriber-expert-pronostic public-widget" aria-labelledby="subscriber-expert-pronostic-title">
              <p className="public-kicker">{t.expert.kicker}</p>
              <h2 id="subscriber-expert-pronostic-title">{t.expert.title}</h2>
              <p>{analysis.expert_commentary}</p>
            </section>
          )}

          <section className="subscriber-composite-scores public-widget" aria-labelledby="subscriber-composite-scores-title">
            <div className="subscriber-section-heading">
              <div>
                <p className="public-kicker">{t.composite.kicker}</p>
                <h2 id="subscriber-composite-scores-title">{t.composite.title}</h2>
                <p>{t.composite.description}</p>
              </div>
            </div>
            <div className="subscriber-composite-table-wrap">
              <table className="subscriber-composite-table">
                <thead>
                  <tr>
                    <th scope="col">{t.composite.rank}</th>
                    <th scope="col">{t.composite.number}</th>
                    <th scope="col">{t.composite.horse}</th>
                    <th scope="col">{t.composite.odds}</th>
                    <th scope="col">{t.composite.form}</th>
                    <th scope="col">{t.composite.score}</th>
                  </tr>
                </thead>
                <tbody>
                  {completeCompositeScores.map(({ horse, index, score }, rank) => (
                    <tr key={`${horseNumber(horse)}-${index}`}>
                      <td>{score === null ? "—" : rank + 1}</td>
                      <td>{horseNumber(horse)}</td>
                      <td>{horseName(horse, unknownHorse)}</td>
                      <td>{firstValue(horse, oddsFields) || "—"}</td>
                      <td>{firstValue(horse, formFields) || "—"}</td>
                      <td>{displayScore(score, intlLocale)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <DisciplineHighlights analysis={analysis} />

          <footer className="subscriber-print-footer">
            <p>{t.footer.disclaimer}</p>
            <span>
              {interpolate(t.footer.credit, { year: new Date().getFullYear() })}
              <br />
              {t.footer.contact}
            </span>
          </footer>

          <details className="subscriber-details public-widget">
            <summary>{t.methodology.summary}</summary>
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
              <li>{t.methodology.ranking}</li>
              <li>{t.methodology.prognosis}</li>
              <li>{t.methodology.modelShortlist}</li>
              <li>{t.methodology.priorityTier}</li>
              <li>{t.methodology.odds}</li>
              <li>{t.methodology.signals}</li>
              {analysis.handicap && <li>{interpolate(t.methodology.handicap, { count: analysis.handicap.penalized_count })}</li>}
              {analysis.model_predictions?.message && <li>{analysis.model_predictions.message}</li>}
              <li>{interpolate(t.methodology.modelVersion, { version: analysis.model_version })}</li>
            </ul>
          </details>
        </>
      )}
      {analysis && !loading && !error && dashboardTab === "combinations" && (
        <CombinationsPanel
          key={selectedRaceDate}
          analysis={analysis}
          plotTwistRows={plotTwistRows}
          apiFetch={apiFetch}
          online={online}
        />
      )}
      <QuinteOddsChart meetingDate={selectedRaceDate} />
    </main>
  );
}

export default function SubscribersPage() {
  return <AccessGate allowedRoles={["demo", "subscriber", "admin"]}><SubscriberDashboard /></AccessGate>;
}

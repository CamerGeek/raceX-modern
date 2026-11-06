"use client";

import { useEffect, useState } from "react";
import { offlineKeys, readOffline, saveOffline } from "./offline-data";
import { apiUrl, parisDate, type Horse, type QuinteAnalysis } from "./race-data";
import { interpolate } from "../i18n/format";
import { useI18n } from "../i18n/provider";

const scoreFields = ["Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score"];
const numberFields = ["N°", "N", "Numero", "NUMERO", "NUM"];

let todayAnalysisRequest: Promise<QuinteAnalysis> | null = null;

function requestTodayAnalysis() {
  if (!todayAnalysisRequest) {
    todayAnalysisRequest = fetch(
      `${apiUrl}/api/v1/races/turfomania/quinte/today/public?date=${parisDate()}`,
    )
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail ?? "");
        }
        return payload as QuinteAnalysis;
      })
      .catch((error: unknown) => {
        todayAnalysisRequest = null;
        throw error;
      });
  }
  return todayAnalysisRequest;
}

function value(row: Horse, fields: string[]) {
  const key = fields.find((field) => row[field] !== null && row[field] !== undefined && row[field] !== "");
  return key ? String(row[key]) : "—";
}

function compositeScore(row: Horse) {
  const raw = value(row, scoreFields).trim().replace(",", ".");
  const score = Number(raw);
  return raw && Number.isFinite(score) ? score : null;
}

function topEight(rows: Horse[]) {
  return rows
    .map((row) => ({ row, score: compositeScore(row) }))
    .filter((item): item is { row: Horse; score: number } => item.score !== null)
    .sort((first, second) => second.score - first.score)
    .slice(0, 8);
}

export default function QuinteTopEight({ initialAnalysis = null }: { initialAnalysis?: QuinteAnalysis | null }) {
  const { messages, intlLocale } = useI18n();
  const t = messages.topEight;
  const [analysis, setAnalysis] = useState<QuinteAnalysis | null>(initialAnalysis);
  const [loading, setLoading] = useState(initialAnalysis === null);
  const [error, setError] = useState("");
  const [cachedAt, setCachedAt] = useState<number | null>(null);

  useEffect(() => {
    if (!initialAnalysis) return;
    void saveOffline(offlineKeys.topEight(parisDate()), initialAnalysis);
  }, [initialAnalysis]);

  useEffect(() => {
    if (initialAnalysis) return;

    const cacheKey = offlineKeys.topEight(parisDate());
    let active = true;
    requestTodayAnalysis()
      .then((result) => {
        if (!active) return;
        setAnalysis(result);
        setCachedAt(null);
        void saveOffline(cacheKey, result);
      })
      .catch(async () => {
        const cached = await readOffline<QuinteAnalysis>(cacheKey);
        if (!active) return;
        if (cached) {
          setAnalysis(cached.payload);
          setCachedAt(cached.savedAt);
          return;
        }
        setError(t.error);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [initialAnalysis, t.error]);

  async function retry() {
    setLoading(true);
    setError("");
    const cacheKey = offlineKeys.topEight(parisDate());
    try {
      const result = await requestTodayAnalysis();
      setAnalysis(result);
      setCachedAt(null);
      void saveOffline(cacheKey, result);
    } catch {
      const cached = await readOffline<QuinteAnalysis>(cacheKey);
      if (cached) {
        setAnalysis(cached.payload);
        setCachedAt(cached.savedAt);
      } else {
        setError(t.error);
      }
    } finally {
      setLoading(false);
    }
  }

  const rankedHorses = analysis ? topEight(analysis.rows) : [];

  return (
    <section className="public-widget free-analysis" aria-labelledby="free-analysis-title" aria-live="polite">
      <div className="free-analysis-heading">
        <div>
          <p className="public-kicker">{t.kicker}</p>
          <h2 id="free-analysis-title">{t.title}</h2>
          <p className="free-analysis-description">{t.description}</p>
        </div>
        {analysis && <span className="free-analysis-count">{interpolate(t.count, { count: analysis.row_count })}</span>}
      </div>

      {cachedAt !== null && (
        <p className="free-analysis-status" role="status">
          {interpolate(messages.cache.savedAt, {
            time: new Intl.DateTimeFormat(intlLocale, {
              timeZone: "Europe/Paris",
              hour: "2-digit",
              minute: "2-digit",
            }).format(new Date(cachedAt)),
          })}
        </p>
      )}

      {loading && (
        <p className="free-analysis-status" role="status">
          {t.loading}
        </p>
      )}
      {!loading && error && (
        <div className="free-analysis-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={retry}>{t.retry}</button>
        </div>
      )}
      {!loading && !error && analysis && rankedHorses.length > 0 && (
        <ul className="free-analysis-list" aria-label={t.listAria}>
          {rankedHorses.map(({ row }, index) => (
            <li key={`${value(row, numberFields)}-${index}`}>
              <strong>{value(row, numberFields)}</strong>
            </li>
          ))}
        </ul>
      )}
      {!loading && !error && analysis && rankedHorses.length === 0 && (
        <p className="free-analysis-status">{t.unavailable}</p>
      )}
    </section>
  );
}

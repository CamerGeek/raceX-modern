"use client";

import { useCallback, useEffect, useState } from "react";
import { interpolate } from "../i18n/format";
import { useI18n } from "../i18n/provider";
import { offlineKeys, readOffline, saveOffline } from "./offline-data";
import { useOnlineStatus } from "./use-online-status";

type OddsPoint = { captured_at: string; odds: number };
type OddsSeries = { number: string; horse_name: string; points: OddsPoint[] };
type OddsHistory = {
  date: string;
  race: { id: string; race_key: string | null; race_type: "flat" | "trot" } | null;
  series: OddsSeries[];
};
type OddsMovement = {
  runner: OddsSeries;
  openingOdds: number;
  latestOdds: number;
  dropPercent: number;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const colors = [
  "#c96f3b", "#1d594b", "#3177a8", "#9a5b9c", "#bf9c26", "#be4c45",
  "#428b72", "#5364a8", "#b65f84", "#6e7b35", "#266f76", "#a36b37",
  "#6550a1", "#3e8c9f", "#915548", "#767676",
];
const chart = { width: 900, height: 390, left: 58, right: 20, top: 20, bottom: 48 };

function niceStep(max: number) {
  const rawStep = max / 5;
  const power = 10 ** Math.floor(Math.log10(rawStep || 1));
  const fraction = rawStep / power;
  const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
  return niceFraction * power;
}

function timeLabel(timestamp: string, intlLocale: string) {
  return new Intl.DateTimeFormat(intlLocale, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  }).format(new Date(timestamp));
}

function formatOdds(odds: number, intlLocale: string) {
  return odds.toLocaleString(intlLocale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function QuinteOddsChart({ meetingDate }: { meetingDate?: string }) {
  const { messages, intlLocale } = useI18n();
  const t = messages.odds;
  const online = useOnlineStatus();
  const [history, setHistory] = useState<OddsHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cachedAt, setCachedAt] = useState<number | null>(null);

  const loadHistory = useCallback(async () => {
    const cacheKey = offlineKeys.odds(meetingDate ?? new Intl.DateTimeFormat("fr-CA", {
      timeZone: "Europe/Paris",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()));
    const applyCached = async () => {
      const cached = await readOffline<OddsHistory>(cacheKey);
      if (!cached) return false;
      setHistory(cached.payload);
      setCachedAt(cached.savedAt);
      setError("");
      return true;
    };
    if (!online) {
      if (!(await applyCached())) setError(t.error);
      setLoading(false);
      return;
    }
    try {
      const dateQuery = meetingDate ? `?date=${encodeURIComponent(meetingDate)}` : "";
      const response = await fetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/odds${dateQuery}`, {
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "");
      setHistory(payload as OddsHistory);
      setCachedAt(null);
      setError("");
      void saveOffline(cacheKey, payload as OddsHistory);
    } catch (loadError) {
      if (!(await applyCached())) {
        setError(loadError instanceof Error && loadError.message ? loadError.message : t.error);
      }
    } finally {
      setLoading(false);
    }
  }, [meetingDate, online, t.error]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadHistory(), 0);
    const interval = window.setInterval(() => void loadHistory(), 5 * 60 * 1000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [loadHistory]);

  const series = history?.series ?? [];
  const allPoints = series.flatMap((runner) => runner.points);
  const hasComparableSamples = series.some((runner) => {
    const timestamps = runner.points
      .map((point) => Date.parse(point.captured_at))
      .filter(Number.isFinite)
      .sort((first, second) => first - second);
    return timestamps.length > 1 && timestamps[0] !== timestamps.at(-1);
  });
  const movements = series
    .map((runner): OddsMovement | null => {
      const points = runner.points
        .filter((point) => Number.isFinite(point.odds) && point.odds > 0 && Number.isFinite(Date.parse(point.captured_at)))
        .sort((first, second) => Date.parse(first.captured_at) - Date.parse(second.captured_at));
      const openingOdds = points[0]?.odds;
      const latestOdds = points.at(-1)?.odds;
      if (openingOdds === undefined || latestOdds === undefined || points.length < 2 || latestOdds >= openingOdds) {
        return null;
      }
      return {
        runner,
        openingOdds,
        latestOdds,
        dropPercent: ((openingOdds - latestOdds) / openingOdds) * 100,
      };
    })
    .filter((movement): movement is OddsMovement => movement !== null)
    .sort((first, second) => second.dropPercent - first.dropPercent);
  const timestampValues = allPoints.map((point) => Date.parse(point.captured_at)).filter(Number.isFinite);
  const firstTimestamp = timestampValues.length ? Math.min(...timestampValues) : 0;
  const lastTimestamp = timestampValues.length ? Math.max(...timestampValues) : 0;
  const maxOdds = Math.max(0, ...allPoints.map((point) => point.odds));
  const step = niceStep(maxOdds || 1);
  const yMax = Math.max(step, Math.ceil(maxOdds / step) * step);
  const plotWidth = chart.width - chart.left - chart.right;
  const plotHeight = chart.height - chart.top - chart.bottom;
  const x = (timestamp: number) =>
    chart.left + (lastTimestamp === firstTimestamp ? plotWidth / 2 : ((timestamp - firstTimestamp) / (lastTimestamp - firstTimestamp)) * plotWidth);
  const y = (odds: number) => chart.top + plotHeight - (odds / yMax) * plotHeight;

  return (
    <section className="public-widget odds-chart-panel" aria-labelledby="odds-chart-title" aria-live="polite">
      <div className="odds-chart-heading">
        <div>
          <p className="public-kicker">{t.kicker}</p>
          <h2 id="odds-chart-title">{t.title}</h2>
          <p className="odds-chart-description">{t.description}</p>
        </div>
        {history?.race && <span className="free-analysis-count">{history.race.race_key ?? "Quinté+"}</span>}
      </div>

      {cachedAt !== null && (
        <p className="odds-chart-cache-note" role="status">
          {interpolate(messages.cache.savedAt, {
            time: new Intl.DateTimeFormat(intlLocale, {
              timeZone: "Europe/Paris",
              hour: "2-digit",
              minute: "2-digit",
            }).format(new Date(cachedAt)),
          })}
        </p>
      )}
      {loading && <p className="free-analysis-status" role="status">{t.loading}</p>}
      {!loading && error && <p className="odds-chart-error" role="alert">{error}</p>}
      {!loading && !error && (!history?.race || allPoints.length === 0) && (
        <p className="free-analysis-status">{t.empty}</p>
      )}
      {!loading && !error && allPoints.length > 0 && (
        <>
          <div className="odds-chart-scroll">
            <svg
              className="odds-chart"
              viewBox={`0 0 ${chart.width} ${chart.height}`}
              role="img"
              aria-label={t.chartAria}
            >
              {Array.from({ length: Math.floor(yMax / step) + 1 }, (_, index) => {
                const odds = index * step;
                const position = y(odds);
                return (
                  <g key={`y-${odds}`}>
                    <line x1={chart.left} x2={chart.width - chart.right} y1={position} y2={position} className="odds-chart-grid" />
                    <text x={chart.left - 10} y={position + 4} textAnchor="end" className="odds-chart-axis">{odds}</text>
                  </g>
                );
              })}
              <line
                x1={chart.left}
                x2={chart.width - chart.right}
                y1={chart.height - chart.bottom}
                y2={chart.height - chart.bottom}
                className="odds-chart-axis-line"
              />
              <text x={chart.left} y={chart.height - 16} textAnchor="start" className="odds-chart-axis">
                {timeLabel(new Date(firstTimestamp).toISOString(), intlLocale)}
              </text>
              {lastTimestamp !== firstTimestamp && (
                <text x={chart.width - chart.right} y={chart.height - 16} textAnchor="end" className="odds-chart-axis">
                  {timeLabel(new Date(lastTimestamp).toISOString(), intlLocale)}
                </text>
              )}
              {series.map((runner, index) => {
                const color = colors[index % colors.length];
                const points = runner.points
                  .map((point) => ({ ...point, timestamp: Date.parse(point.captured_at) }))
                  .filter((point) => Number.isFinite(point.timestamp))
                  .sort((first, second) => first.timestamp - second.timestamp);
                if (!points.length) return null;
                const pointString = points.map((point) => `${x(point.timestamp)},${y(point.odds)}`).join(" ");
                return (
                  <g key={runner.number}>
                    {points.length > 1 && (
                      <polyline points={pointString} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
                    )}
                    {points.map((point) => (
                      <circle key={`${point.captured_at}-${runner.number}`} cx={x(point.timestamp)} cy={y(point.odds)} r="4" fill={color}>
                        <title>
                          {interpolate(t.tooltip, {
                            number: runner.number,
                            name: runner.horse_name,
                            odds: point.odds.toFixed(2),
                            time: timeLabel(point.captured_at, intlLocale),
                          })}
                        </title>
                      </circle>
                    ))}
                  </g>
                );
              })}
            </svg>
          </div>
          <section className="odds-movers" aria-labelledby="odds-movers-title">
            <h3 id="odds-movers-title">{t.moversTitle}</h3>
            {movements.length > 0 ? (
              <ol>
                {movements.slice(0, 5).map(({ runner, openingOdds, latestOdds, dropPercent }) => (
                  <li key={runner.number}>
                    <strong>{interpolate(t.horse, { number: runner.number })}{runner.horse_name ? ` · ${runner.horse_name}` : ""}</strong>
                    <span>{formatOdds(openingOdds, intlLocale)} → {formatOdds(latestOdds, intlLocale)}</span>
                    <b>−{dropPercent.toLocaleString(intlLocale, { maximumFractionDigits: 1 })} %</b>
                  </li>
                ))}
              </ol>
            ) : !hasComparableSamples ? (
              <>
                <p>{t.singleSample}</p>
                <ol>
                  {series.map((runner) => {
                    const latestPoint = runner.points
                      .filter((point) => Number.isFinite(point.odds) && point.odds > 0 && Number.isFinite(Date.parse(point.captured_at)))
                      .sort((first, second) => Date.parse(first.captured_at) - Date.parse(second.captured_at))
                      .at(-1);
                    return latestPoint ? (
                      <li key={runner.number}>
                        <strong>{interpolate(t.horse, { number: runner.number })}{runner.horse_name ? ` · ${runner.horse_name}` : ""}</strong>
                        <span>{t.currentOdds}</span>
                        <b className="odds-current-value">{formatOdds(latestPoint.odds, intlLocale)}</b>
                      </li>
                    ) : null;
                  })}
                </ol>
              </>
            ) : (
              <p>{t.noDrops}</p>
            )}
          </section>
          <ul className="odds-chart-legend" aria-label={t.legendAria}>
            {series.map((runner, index) => (
              <li key={runner.number}>
                <span style={{ backgroundColor: colors[index % colors.length] }} />
                <strong>{runner.number}</strong>
                {runner.horse_name && <span>{runner.horse_name}</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="odds-chart-footnote">{t.footnote}</p>
    </section>
  );
}

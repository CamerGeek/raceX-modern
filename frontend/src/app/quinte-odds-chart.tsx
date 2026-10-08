"use client";

import { useCallback, useEffect, useState } from "react";

type OddsPoint = { captured_at: string; odds: number };
type OddsSeries = { number: string; horse_name: string; points: OddsPoint[] };
type OddsHistory = {
  date: string;
  race: { id: string; race_key: string | null; race_type: "flat" | "trot" } | null;
  series: OddsSeries[];
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

function timeLabel(timestamp: string) {
  return new Intl.DateTimeFormat("fr-FR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Paris",
  }).format(new Date(timestamp));
}

export default function QuinteOddsChart() {
  const [history, setHistory] = useState<OddsHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHistory = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/odds`, {
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Impossible de charger l’historique des cotes.");
      setHistory(payload as OddsHistory);
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Impossible de charger l’historique des cotes.");
    } finally {
      setLoading(false);
    }
  }, []);

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
          <p className="public-kicker">SUIVI DU MARCHÉ</p>
          <h2 id="odds-chart-title">Évolution des cotes</h2>
          <p className="odds-chart-description">Un point toutes les 30 minutes · heures de Paris</p>
        </div>
        {history?.race && <span className="free-analysis-count">{history.race.race_key ?? "Quinté+"}</span>}
      </div>

      {loading && <p className="free-analysis-status" role="status">Chargement de l’historique des cotes…</p>}
      {!loading && error && <p className="odds-chart-error" role="alert">{error}</p>}
      {!loading && !error && (!history?.race || allPoints.length === 0) && (
        <p className="free-analysis-status">
          Les premières cotes seront affichées après le prochain relevé programmé.
        </p>
      )}
      {!loading && !error && allPoints.length > 0 && (
        <>
          <div className="odds-chart-scroll">
            <svg
              className="odds-chart"
              viewBox={`0 0 ${chart.width} ${chart.height}`}
              role="img"
              aria-label="Graphique de l’évolution des cotes du Quinté+, une ligne colorée par cheval"
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
                {timeLabel(new Date(firstTimestamp).toISOString())}
              </text>
              {lastTimestamp !== firstTimestamp && (
                <text x={chart.width - chart.right} y={chart.height - 16} textAnchor="end" className="odds-chart-axis">
                  {timeLabel(new Date(lastTimestamp).toISOString())}
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
                        <title>{`N° ${runner.number} ${runner.horse_name}: ${point.odds.toFixed(2)} à ${timeLabel(point.captured_at)}`}</title>
                      </circle>
                    ))}
                  </g>
                );
              })}
            </svg>
          </div>
          <ul className="odds-chart-legend" aria-label="Chevaux représentés sur le graphique">
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
      <p className="odds-chart-footnote">Les cotes sont indicatives et peuvent évoluer entre deux relevés.</p>
    </section>
  );
}

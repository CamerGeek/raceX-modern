"use client";

import { useEffect, useState } from "react";

type Horse = Record<string, string | number | boolean | null>;

type QuinteAnalysis = {
  race_id: string;
  race_type: "flat" | "trot";
  row_count: number;
  rows: Horse[];
  race_details: string;
  model_version: string;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const scoreFields = ["Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score"];
const numberFields = ["N°", "N", "Numero", "NUMERO", "NUM"];

let todayAnalysisRequest: Promise<QuinteAnalysis> | null = null;

function localDate() {
  const today = new Date();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${today.getFullYear()}-${month}-${day}`;
}

function requestTodayAnalysis() {
  if (!todayAnalysisRequest) {
    todayAnalysisRequest = fetch(`${apiUrl}/api/v1/races/turfomania/quinte/today/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date: localDate() }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail ?? "Impossible de charger l'analyse du Quinté+.");
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

export default function QuinteTopEight() {
  const [analysis, setAnalysis] = useState<QuinteAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    requestTodayAnalysis()
      .then((result) => {
        if (active) setAnalysis(result);
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(requestError instanceof Error ? requestError.message : "Impossible de charger l'analyse du Quinté+.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function retry() {
    setLoading(true);
    setError("");
    requestTodayAnalysis()
      .then(setAnalysis)
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : "Impossible de charger l'analyse du Quinté+.");
      })
      .finally(() => setLoading(false));
  }

  const rankedHorses = analysis ? topEight(analysis.rows) : [];

  return (
    <section className="public-widget free-analysis" aria-labelledby="free-analysis-title" aria-live="polite">
      <div className="free-analysis-heading">
        <div>
          <p className="public-kicker">ANALYSE GRATUITE DU JOUR</p>
          <h2 id="free-analysis-title">Top 8 par score composite</h2>
          <p className="free-analysis-description">
            Classement calculé à partir des partants et des signaux de la course.
          </p>
        </div>
        {analysis && <span className="free-analysis-count">{analysis.row_count} partants</span>}
      </div>

      {loading && <p className="free-analysis-status" role="status">Analyse du Quinté+ en cours…</p>}
      {!loading && error && (
        <div className="free-analysis-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={retry}>Réessayer</button>
        </div>
      )}
      {!loading && !error && analysis && rankedHorses.length > 0 && (
        <ul className="free-analysis-list" aria-label="Numéros des huit chevaux les mieux classés">
          {rankedHorses.map(({ row }, index) => (
            <li key={`${value(row, numberFields)}-${index}`}>
              <strong>{value(row, numberFields)}</strong>
            </li>
          ))}
        </ul>
      )}
      {!loading && !error && analysis && rankedHorses.length === 0 && (
        <p className="free-analysis-status">Le score composite n’est pas disponible pour cette course.</p>
      )}
    </section>
  );
}

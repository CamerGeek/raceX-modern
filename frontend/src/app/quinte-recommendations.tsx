"use client";

import { interpolate } from "../i18n/format";
import { useI18n } from "../i18n/provider";

type Horse = Record<string, string | number | boolean | null>;

export type QuinteModelPredictions = {
  status: "ready" | "unsupported" | "unavailable";
  rows: Horse[];
  message: string | null;
};

type QuinteRecommendationsProps = {
  modelPredictions: QuinteModelPredictions | null;
  plotTwistRows: PlotTwistItem[];
};

export type PlotTwistItem = {
  horse: Horse;
  score: number;
  rank: number;
  nearMean: boolean;
  nearMedian: boolean;
};

const horseNumberFields = ["NUMERO", "N°", "N", "Numero", "N?", "NUM"];
const deepScoreFields = ["place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score"];
const winScoreFields = ["p_win", "P_WIN", ...deepScoreFields];
const priorityTierFields = ["bet_tier", "priority_tier", "Priority tier", "Priority Tier"];

function horseNumber(row: Horse) {
  const key = horseNumberFields.find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  if (!key) return "";
  return String(row[key]).trim().replace(/\.0$/, "");
}

function horseName(row: Horse, fallback: string) {
  const key = ["CHEVAL", "Cheval", "NOM", "NAME"].find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  return key ? String(row[key]) : fallback;
}

export function getModelShortlistRows(predictions: QuinteModelPredictions | null) {
  if (predictions?.status !== "ready") return [];

  return predictions.rows
    .map((row, index) => {
      const scoreKey = deepScoreFields.find((field) =>
        row[field] !== null && row[field] !== undefined && row[field] !== "",
      );
      const rawScore = scoreKey ? String(row[scoreKey]).trim().replace(",", ".") : "";
      const score = Number(rawScore);
      return { row, index, score: rawScore && Number.isFinite(score) ? score : null };
    })
    .filter((item): item is { row: Horse; index: number; score: number } => item.score !== null)
    .sort((first, second) => second.score - first.score || first.index - second.index)
    .map(({ row }) => row)
    .filter((row) => Boolean(horseNumber(row)))
    .slice(0, 8);
}

export function getModelWinRows(predictions: QuinteModelPredictions | null) {
  if (predictions?.status !== "ready") return [];

  return predictions.rows
    .map((row, index) => {
      const scoreKey = winScoreFields.find((field) =>
        row[field] !== null && row[field] !== undefined && row[field] !== "",
      );
      const rawScore = scoreKey ? String(row[scoreKey]).trim().replace(",", ".") : "";
      const score = Number(rawScore);
      return { row, index, score: rawScore && Number.isFinite(score) ? score : null };
    })
    .filter((item): item is { row: Horse; index: number; score: number } => item.score !== null)
    .sort((first, second) => second.score - first.score || first.index - second.index)
    .map(({ row }) => row)
    .filter((row) => Boolean(horseNumber(row)));
}

export function winScoreOf(row: Horse) {
  const key = winScoreFields.find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  const raw = key ? String(row[key]).trim().replace(",", ".") : "";
  const score = Number(raw);
  return raw && Number.isFinite(score) ? raw : "";
}

function hasShodDef(row: Horse) {
  const defField = Object.keys(row).find((field) =>
    ["DEF.", "DEF"].includes(field.trim().toUpperCase()),
  );
  if (!defField) return false;
  const def = row[defField];
  if (def === null || (typeof def === "number" && Number.isNaN(def))) return true;
  if (typeof def !== "string") return false;
  const normalizedDef = def.trim().toLowerCase();
  return normalizedDef === "" || normalizedDef === "-" || normalizedDef === "nan";
}

function shodHorseRows(rows: Horse[]) {
  return rows.filter((row) => hasShodDef(row) && Boolean(horseNumber(row)));
}

export function ShodHorsesCard({ rows }: { rows: Horse[] }) {
  const t = useI18n().messages.shod;
  const shodHorses = shodHorseRows(rows);
  const allHorsesShod = rows.length > 0 && rows.every(hasShodDef);

  return (
    <section className="public-widget quinte-pick-card" aria-label={t.aria}>
      <div>
        <p className="public-kicker">{t.kicker}</p>
        <h2>{t.title}</h2>
        <p className="quinte-pick-description">{t.description}</p>
      </div>
      {allHorsesShod ? (
        <p className="free-analysis-status">{t.all}</p>
      ) : shodHorses.length > 0 ? (
        <ol className="free-analysis-list" aria-label={t.aria}>
          {shodHorses.map((horse, index) => (
            <li key={`${horseNumber(horse)}-${index}`}>
              <strong>{horseNumber(horse)}</strong>
            </li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">{t.none}</p>
      )}
    </section>
  );
}

function PlotTwistCard({ rows }: { rows: PlotTwistItem[] }) {
  const { messages, intlLocale } = useI18n();
  const t = messages.recommendations;
  const displayScore = (score: number) =>
    score.toLocaleString(intlLocale, { maximumFractionDigits: 2 });

  return (
    <section className="subscriber-discipline-card subscriber-plot-twist" aria-labelledby="subscriber-plot-twist-title">
      <h3 id="subscriber-plot-twist-title">{t.plotTwistTitle}</h3>
      <p>{t.plotTwistDescription}</p>
      {rows.length > 0 ? (
        <ol>
          {rows.map(({ horse, score, rank, nearMean, nearMedian }, index) => (
            <li key={`plot-twist-${horseNumber(horse)}-${index}`}>
              <strong>{horseNumber(horse)}</strong>
              <span>{horseName(horse, t.unknownHorse)} · {interpolate(t.plotTwistRank, { rank })}</span>
              <b>
                {displayScore(score)}
                {" · "}
                {nearMean && nearMedian ? t.nearMeanMedian : nearMean ? t.nearMean : t.nearMedian}
              </b>
            </li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">{t.plotTwistEmpty}</p>
      )}
    </section>
  );
}

function modelShortlist(predictions: QuinteModelPredictions | null) {
  return getModelShortlistRows(predictions).map(horseNumber);
}

function priorityTierShortlist(predictions: QuinteModelPredictions | null) {
  if (predictions?.status !== "ready") return [];

  return predictions.rows
    .map((row, index) => {
      const number = horseNumber(row);
      const tierKey = priorityTierFields.find((field) =>
        row[field] !== null && row[field] !== undefined && row[field] !== "",
      );
      const rawTier = tierKey ? String(row[tierKey]).trim().replace(",", ".") : "";
      const tier = Number(rawTier);
      return { number, tier, index };
    })
    .filter((item) => Boolean(item.number) && Number.isInteger(item.tier) && item.tier > 0)
    .sort((first, second) => first.tier - second.tier || first.index - second.index);
}

function PickCard({
  title,
  description,
  numbers,
  emptyMessage,
}: {
  title: string;
  description: string;
  numbers: string[];
  emptyMessage: string;
}) {
  const t = useI18n().messages.recommendations;

  return (
    <section className="public-widget quinte-pick-card" aria-label={title}>
      <div>
        <p className="public-kicker">{t.pickKicker}</p>
        <h2>{title}</h2>
        <p className="quinte-pick-description">{description}</p>
      </div>
      {numbers.length > 0 ? (
        <ol className="free-analysis-list" aria-label={interpolate(t.numbersAria, { title })}>
          {numbers.map((number, index) => (
            <li key={`${number}-${index}`}><strong>{number}</strong></li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">{emptyMessage}</p>
      )}
    </section>
  );
}

export function PriorityTierPickCard({
  predictions,
}: {
  predictions: QuinteModelPredictions | null;
}) {
  const t = useI18n().messages.recommendations;
  const horses = priorityTierShortlist(predictions);
  const tiers = horses.reduce<{ tier: number; numbers: string[] }[]>((groups, horse) => {
    const group = groups.find((item) => item.tier === horse.tier);
    if (group) {
      group.numbers.push(horse.number);
    } else {
      groups.push({ tier: horse.tier, numbers: [horse.number] });
    }
    return groups;
  }, []);
  const message = predictions?.status === "ready"
    ? t.priorityNone
    : predictions?.message ?? t.priorityUnavailable;

  return (
    <section className="public-widget quinte-pick-card" aria-label={t.priorityAria}>
      <div>
        <p className="public-kicker">{t.pickKicker}</p>
        <h2>{t.priorityTitle}</h2>
        <p className="quinte-pick-description">{t.priorityDescription}</p>
      </div>
      {tiers.length > 0 ? (
        <ol className="priority-tier-list" aria-label={t.priorityListAria}>
          {tiers.map(({ tier, numbers }) => (
            <li key={tier}>
              <strong>{interpolate(t.tier, { tier })}</strong>
              <span>{numbers.join(" ")}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">{message}</p>
      )}
    </section>
  );
}

export default function QuinteRecommendations({
  modelPredictions,
  plotTwistRows,
}: QuinteRecommendationsProps) {
  const t = useI18n().messages.recommendations;
  const modelNumbers = modelShortlist(modelPredictions);
  const modelMessage = modelPredictions?.status === "ready"
    ? t.modelEmptyReady
    : modelPredictions?.message ?? t.modelUnavailable;

  return (
    <div className="quinte-picks-grid">
      <PickCard
        title={t.modelTitle}
        description={t.modelDescription}
        numbers={modelNumbers}
        emptyMessage={modelMessage}
      />
      <PriorityTierPickCard predictions={modelPredictions} />
      <PlotTwistCard rows={plotTwistRows} />
    </div>
  );
}

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
const priorityTierFields = ["bet_tier", "priority_tier", "Priority tier", "Priority Tier"];

function horseNumber(row: Horse) {
  const key = horseNumberFields.find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  if (!key) return "";
  return String(row[key]).trim().replace(/\.0$/, "");
}

function horseName(row: Horse) {
  const key = ["CHEVAL", "Cheval", "NOM", "NAME"].find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  return key ? String(row[key]) : "Cheval sans nom";
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
  const shodHorses = shodHorseRows(rows);
  const allHorsesShod = rows.length > 0 && rows.every(hasShodDef);

  return (
    <section className="public-widget quinte-pick-card" aria-label="Chevaux ferrés">
      <div>
        <p className="public-kicker">INDICATION FERRURE</p>
        <h2>Chevaux ferrés</h2>
        <p className="quinte-pick-description">
          Partants ferrés selon DEF. (valeur vide, « - » ou nan).
        </p>
      </div>
      {allHorsesShod ? (
        <p className="free-analysis-status">Tous les chevaux de cette course sont ferrés.</p>
      ) : shodHorses.length > 0 ? (
        <ol className="free-analysis-list" aria-label="Chevaux ferrés">
          {shodHorses.map((horse, index) => (
            <li key={`${horseNumber(horse)}-${index}`}>
              <strong>{horseNumber(horse)}</strong>
            </li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">Aucun partant ferré identifié pour cette course.</p>
      )}
    </section>
  );
}

function displayScore(score: number) {
  return score.toLocaleString("fr-FR", { maximumFractionDigits: 2 });
}

function PlotTwistCard({ rows }: { rows: PlotTwistItem[] }) {
  return (
    <section className="subscriber-discipline-card subscriber-plot-twist" aria-labelledby="subscriber-plot-twist-title">
      <h3 id="subscriber-plot-twist-title">Plot twist · chevaux à surveiller</h3>
      <p>
        Partants hors du top 8 composite dont le score se situe à ±0,05 de la moyenne ou de la médiane.
        C’est un repère complémentaire, pas une garantie de performance.
      </p>
      {rows.length > 0 ? (
        <ol>
          {rows.map(({ horse, score, rank, nearMean, nearMedian }, index) => (
            <li key={`plot-twist-${horseNumber(horse)}-${index}`}>
              <strong>{horseNumber(horse)}</strong>
              <span>{horseName(horse)} · rang {rank}</span>
              <b>
                {displayScore(score)}
                {" · "}
                {nearMean && nearMedian ? "moyenne · médiane" : nearMean ? "moyenne" : "médiane"}
              </b>
            </li>
          ))}
        </ol>
      ) : (
        <p className="free-analysis-status">Aucun partant hors top 8 ne correspond à ce repère pour cette course.</p>
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
  return (
    <section className="public-widget quinte-pick-card" aria-label={title}>
      <div>
        <p className="public-kicker">SÉLECTION DU JOUR</p>
        <h2>{title}</h2>
        <p className="quinte-pick-description">{description}</p>
      </div>
      {numbers.length > 0 ? (
        <ol className="free-analysis-list" aria-label={`Numéros sélectionnés : ${title}`}>
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
    ? "Aucun cheval n’a de niveau de priorité disponible."
    : predictions?.message ?? "Les niveaux de priorité du modèle ne sont pas disponibles pour cette course.";

  return (
    <section className="public-widget quinte-pick-card" aria-label="Priorité des chevaux selon le modèle">
      <div>
        <p className="public-kicker">SÉLECTION DU JOUR</p>
        <h2>Priorité du modèle</h2>
        <p className="quinte-pick-description">Chevaux classés par niveau de priorité du modèle, Tier 1 en premier.</p>
      </div>
      {tiers.length > 0 ? (
        <ol className="priority-tier-list" aria-label="Chevaux classés par niveau de priorité">
          {tiers.map(({ tier, numbers }) => (
            <li key={tier}>
              <strong>Tier {tier}:</strong>
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
  const modelNumbers = modelShortlist(modelPredictions);
  const modelMessage = modelPredictions?.status === "ready"
    ? "Le modèle n’a pas fourni de chevaux classables."
    : modelPredictions?.message ?? "Le Model Shortlist n’est pas disponible pour cette course.";

  return (
    <div className="quinte-picks-grid">
      <PickCard
        title="Model Shortlist(Choix du modele d'IA)"
        description="Jusqu’à 8 numéros classés par deep score décroissant."
        numbers={modelNumbers}
        emptyMessage={modelMessage}
      />
      <PriorityTierPickCard predictions={modelPredictions} />
      <PlotTwistCard rows={plotTwistRows} />
    </div>
  );
}

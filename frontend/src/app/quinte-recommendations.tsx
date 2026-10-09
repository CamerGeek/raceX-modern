type Horse = Record<string, string | number | boolean | null>;

export type QuinteModelPredictions = {
  status: "ready" | "unsupported" | "unavailable";
  rows: Horse[];
  message: string | null;
};

type QuinteRecommendationsProps = {
  prognosis: Horse[];
  modelPredictions: QuinteModelPredictions | null;
};

const horseNumberFields = ["NUMERO", "N°", "N", "Numero", "N?", "NUM"];
const deepScoreFields = ["place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score"];

function horseNumber(row: Horse) {
  const key = horseNumberFields.find((field) =>
    row[field] !== null && row[field] !== undefined && row[field] !== "",
  );
  if (!key) return "";
  return String(row[key]).trim().replace(/\.0$/, "");
}

function numberList(rows: Horse[]) {
  return rows
    .map(horseNumber)
    .filter((number): number is string => Boolean(number))
    .slice(0, 8);
}

function modelShortlist(predictions: QuinteModelPredictions | null) {
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
    .map(({ row }) => horseNumber(row))
    .filter(Boolean)
    .slice(0, 8);
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

export default function QuinteRecommendations({
  prognosis,
  modelPredictions,
}: QuinteRecommendationsProps) {
  const flashNumbers = numberList(prognosis);
  const modelNumbers = modelShortlist(modelPredictions);
  const modelMessage = modelPredictions?.status === "ready"
    ? "Le modèle n’a pas fourni de chevaux classables."
    : modelPredictions?.message ?? "Le Model Shortlist n’est pas disponible pour cette course.";

  return (
    <div className="quinte-picks-grid">
      <PickCard
        title="Notre Prono Flash"
        description="Ordre de la sélection issue de la prognosis de la course."
        numbers={flashNumbers}
        emptyMessage="Notre Prono Flash n’est pas disponible pour cette course."
      />
      <PickCard
        title="Model Shortlist"
        description="Jusqu’à 8 numéros classés par deep score décroissant."
        numbers={modelNumbers}
        emptyMessage={modelMessage}
      />
    </div>
  );
}

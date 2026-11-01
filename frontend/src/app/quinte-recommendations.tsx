type Horse = Record<string, string | number | boolean | null>;

export type QuinteModelPredictions = {
  status: "ready" | "unsupported" | "unavailable";
  rows: Horse[];
  message: string | null;
};

type QuinteRecommendationsProps = {
  prognosis: Horse[];
  modelPredictions: QuinteModelPredictions | null;
  raceType: "flat" | "trot" | "obstacles";
  rows: Horse[];
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
  return key ? String(row[key]).trim() : "Cheval sans nom";
}

function numberList(rows: Horse[]) {
  return rows
    .map(horseNumber)
    .filter((number): number is string => Boolean(number))
    .slice(0, 8);
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

function shodHorseRows(rows: Horse[]) {
  return rows.filter((row) => {
    const defField = ["DEF.", "DEF", "Def"].find((field) =>
      Object.prototype.hasOwnProperty.call(row, field),
    );
    if (!defField) return false;
    const def = row[defField];
    return def === null || (typeof def === "string" && def.trim() === "");
  }).filter((row) => Boolean(horseNumber(row)));
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
      {horses.length > 0 ? (
        <ol className="priority-tier-list" aria-label="Chevaux classés par niveau de priorité">
          {horses.map(({ number, tier }, index) => (
            <li key={`${number}-${index}`}>
              <strong>{number}</strong>
              <span>Tier {tier}</span>
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
  prognosis,
  modelPredictions,
  raceType,
  rows,
}: QuinteRecommendationsProps) {
  const flashNumbers = numberList(prognosis);
  const modelNumbers = modelShortlist(modelPredictions);
  const shodHorses = raceType === "trot" ? shodHorseRows(rows) : [];
  const modelMessage = modelPredictions?.status === "ready"
    ? "Le modèle n’a pas fourni de chevaux classables."
    : modelPredictions?.message ?? "Le Model Shortlist n’est pas disponible pour cette course.";

  return (
    <div className="quinte-picks-grid">
      <PickCard
        title="Prono Flash"
        description="Ordre de la sélection issue d'un pronostic de la course généré automatiquement."
        numbers={flashNumbers}
        emptyMessage="Notre Prono Flash n’est pas disponible pour cette course."
      />
      <PickCard
        title="Model Shortlist(Choix du modele d'IA)"
        description="Jusqu’à 8 numéros classés par deep score décroissant."
        numbers={modelNumbers}
        emptyMessage={modelMessage}
      />
      <PriorityTierPickCard predictions={modelPredictions} />
      {raceType === "trot" && (
        <section className="public-widget quinte-pick-card" aria-label="Chevaux ferrés">
          <div>
            <p className="public-kicker">INDICATION FERRURE</p>
            <h2>Chevaux ferrés</h2>
            <p className="quinte-pick-description">
              Partants avec DEF. non renseigné (valeur nulle).
            </p>
          </div>
          {shodHorses.length > 0 ? (
            <ol className="priority-tier-list" aria-label="Chevaux ferrés">
              {shodHorses.map((horse, index) => (
                <li key={`${horseNumber(horse)}-${index}`}>
                  <strong>N° {horseNumber(horse)}</strong>
                  <span>{horseName(horse)}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="free-analysis-status">Aucun partant ferré identifié pour cette course.</p>
          )}
        </section>
      )}
    </div>
  );
}

"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getModelShortlistRows,
  ReadyTicketsGrid,
  type PlotTwistItem,
  type QuinteModelPredictions,
  type ReadyTicket,
} from "../quinte-recommendations";
import { interpolate } from "../../i18n/format";
import { useI18n } from "../../i18n/provider";

type Horse = Record<string, string | number | boolean | null>;

type CombinationAnalysis = {
  race_id: string;
  rows: Horse[];
  non_partant_numbers: string[];
  model_predictions: QuinteModelPredictions | null;
};

type CombinationPlan = {
  race_type: string;
  combination_size: number;
  ready_tickets?: ReadyTicket[];
  base: string[];
  substitutes?: string[];
  combinations: string[][];
};

type SavedCombination = {
  id: string;
  name: string;
  created_at: string;
  plan: CombinationPlan;
};

type CombinationsPanelProps = {
  analysis: CombinationAnalysis;
  plotTwistRows: PlotTwistItem[];
  apiFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  online: boolean;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const GAME_OPTIONS = [
  { size: 5, label: "gameQuinte" as const, maxTickets: 56 },
  { size: 4, label: "gameQuarte" as const, maxTickets: 70 },
  { size: 3, label: "gameTierce" as const, maxTickets: 56 },
];
const DEFAULT_GAME_SIZE = 5;
const numberFields = ["N°", "N", "Numero", "NUMERO", "NUM"];
const nameFields = ["CHEVAL", "Cheval", "NOM", "NAME"];
const scoreFields = ["Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score"];

function normalizeNumber(value: unknown) {
  return String(value ?? "").trim().replace(/\.0$/, "");
}

function firstValue(row: Horse, fields: string[]) {
  const field = fields.find((key) => row[key] !== null && row[key] !== undefined && row[key] !== "");
  return field ? String(row[field]) : "";
}

function scoreOf(row: Horse) {
  const raw = firstValue(row, scoreFields).trim().replace(",", ".");
  const score = Number(raw);
  return raw && Number.isFinite(score) ? score : null;
}

function orderedStarters(analysis: CombinationAnalysis) {
  const excluded = new Set(analysis.non_partant_numbers.map(normalizeNumber));
  const seen = new Set<string>();
  return analysis.rows
    .map((horse, index) => ({
      horse,
      index,
      number: normalizeNumber(firstValue(horse, numberFields)),
      score: scoreOf(horse),
    }))
    .filter(({ number }) => number && !excluded.has(number))
    .filter(({ number }) => {
      if (seen.has(number)) return false;
      seen.add(number);
      return true;
    })
    .sort((first, second) => {
      if (first.score === null) return second.score === null ? first.index - second.index : 1;
      if (second.score === null) return -1;
      return second.score - first.score || first.index - second.index;
    })
    .map(({ horse, number, score }) => ({
      number,
      name: firstValue(horse, nameFields),
      score,
    }));
}

function CombinationResults({
  plan,
  onSave,
  onPrint,
  saving = false,
  saveDisabled = false,
  threeColumns = false,
}: {
  plan: CombinationPlan;
  onSave?: () => void;
  onPrint?: () => void;
  saving?: boolean;
  saveDisabled?: boolean;
  threeColumns?: boolean;
}) {
  const { messages } = useI18n();
  const t = messages.subscribers.combinations;
  const base = new Set(plan.base);
  const substitutes = plan.substitutes ?? [];
  const readyTickets = plan.ready_tickets ?? [];
  return (
    <div className="combination-results">
      {readyTickets.length > 0 && (
        <div className="ready-tickets">
          <h4>{t.readyTitle}</h4>
          <ReadyTicketsGrid tickets={readyTickets} labels={t} />
        </div>
      )}
      <p className="muted-result">
        {interpolate(t.resultCount, { count: plan.combinations.length, size: plan.combination_size })}
      </p>
      <p className="muted-result">
        {plan.base.length
          ? interpolate(t.baseSummary, { numbers: plan.base.join(" · ") })
          : t.baseEmpty}
        {substitutes.length > 0 && (
          <> — {interpolate(t.substitutesSummary, { numbers: substitutes.join(" · ") })}</>
        )}
      </p>
      <div className={`combination-grid${threeColumns ? " combination-grid-three-columns" : ""}`}>
        {plan.combinations.map((combination, index) => (
          <div className="combination-row" key={`combination-${index}`}>
            <strong>{String(index + 1).padStart(2, "0")}</strong>
            {combination.map((number) => (
              <span className={base.has(number) ? "base-pick" : ""} key={number}>{number}</span>
            ))}
          </div>
        ))}
      </div>
      {(onSave || onPrint) && (
        <div className="combination-result-actions">
          {onSave && (
            <button type="button" onClick={onSave} disabled={saving || saveDisabled}>
              {saving ? t.saving : t.save}
            </button>
          )}
          {onPrint && <button type="button" onClick={onPrint}>{t.print}</button>}
        </div>
      )}
    </div>
  );
}

export default function CombinationsPanel({ analysis, plotTwistRows, apiFetch, online }: CombinationsPanelProps) {
  const { messages, intlLocale } = useI18n();
  const t = messages.subscribers.combinations;
  const [combinationSize, setCombinationSize] = useState(DEFAULT_GAME_SIZE);
  const maxBase = combinationSize - 1;
  const maxTickets = GAME_OPTIONS.find(({ size }) => size === combinationSize)?.maxTickets ?? 56;
  const starters = useMemo(() => orderedStarters(analysis), [analysis]);
  const starterNumbers = useMemo(() => new Set(starters.map(({ number }) => number)), [starters]);
  const suggestedBase = useMemo(() => {
    const shortlist = getModelShortlistRows(analysis.model_predictions)
      .map((row) => normalizeNumber(firstValue(row, numberFields)))
      .filter((number) => starterNumbers.has(number));
    const seeds = shortlist.length > 0 ? shortlist : starters.map(({ number }) => number);
    return [...new Set(seeds)].slice(0, Math.min(3, combinationSize - 1));
  }, [analysis.model_predictions, starters, starterNumbers, combinationSize]);
  const plotTwistNumbers = useMemo(
    () => plotTwistRows
      .map(({ horse }) => normalizeNumber(firstValue(horse, numberFields)))
      .filter((number) => starterNumbers.has(number)),
    [plotTwistRows, starterNumbers],
  );
  const [base, setBase] = useState<string[]>(suggestedBase);
  const [associates, setAssociates] = useState<string[]>([]);
  const [autoPlan, setAutoPlan] = useState<CombinationPlan | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [autoError, setAutoError] = useState("");
  const [customPlan, setCustomPlan] = useState<CombinationPlan | null>(null);
  const [customLoading, setCustomLoading] = useState(false);
  const [customError, setCustomError] = useState("");
  const [savedPlans, setSavedPlans] = useState<SavedCombination[]>([]);
  const [saveName, setSaveName] = useState("");
  const [savedError, setSavedError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [loadedSavedRace, setLoadedSavedRace] = useState<string | null>(null);
  const [savingPlan, setSavingPlan] = useState(false);
  const [printingTarget, setPrintingTarget] = useState<string | null>(null);
  const savedLoading = online && loadedSavedRace !== analysis.race_id && !savedError;

  useEffect(() => {
    if (!online) return;
    let active = true;
    void (async () => {
      try {
        const response = await apiFetch(`${apiUrl}/api/v1/races/${analysis.race_id}/combinations/saved`, {
          cache: "no-store",
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(typeof payload.detail === "string" && payload.detail ? payload.detail : t.savedLoadError);
        }
        if (active) setSavedPlans(Array.isArray(payload.saved_combinations) ? payload.saved_combinations : []);
      } catch (error) {
        if (active) setSavedError(error instanceof Error && error.message ? error.message : t.savedLoadError);
      } finally {
        if (active) setLoadedSavedRace(analysis.race_id);
      }
    })();
    return () => {
      active = false;
    };
  }, [analysis.race_id, apiFetch, online, t.savedLoadError]);

  useEffect(() => {
    if (!printingTarget) return;
    document.body.classList.add("printing-combination");
    const finishPrinting = () => setPrintingTarget(null);
    window.addEventListener("afterprint", finishPrinting, { once: true });
    return () => {
      document.body.classList.remove("printing-combination");
      window.removeEventListener("afterprint", finishPrinting);
    };
  }, [printingTarget]);

  async function requestPlan(path: string, body?: Record<string, unknown>) {
    const response = await apiFetch(`${apiUrl}/api/v1/races/${analysis.race_id}${path}`, {
      method: "POST",
      ...(body
        ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
        : {}),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(typeof payload.detail === "string" && payload.detail ? payload.detail : t.error);
    }
    return payload as CombinationPlan;
  }

  async function loadAutoPlan() {
    setAutoError("");
    if (!online) {
      setAutoError(t.offline);
      return;
    }
    setAutoLoading(true);
    try {
      setAutoPlan(await requestPlan("/combinations", { combination_size: combinationSize }));
    } catch (error) {
      setAutoError(error instanceof Error && error.message ? error.message : t.error);
    } finally {
      setAutoLoading(false);
    }
  }

  function toggleBase(number: string) {
    setCustomError("");
    setCustomPlan(null);
    if (base.includes(number)) {
      setBase(base.filter((selected) => selected !== number));
      return;
    }
    if (base.length >= maxBase) {
      setCustomError(interpolate(t.validationBaseMax, { maxBase, size: combinationSize }));
      return;
    }
    setAssociates(associates.filter((selected) => selected !== number));
    setBase([...base, number]);
  }

  function toggleAssociate(number: string) {
    setCustomError("");
    setCustomPlan(null);
    if (associates.includes(number)) {
      setAssociates(associates.filter((selected) => selected !== number));
      return;
    }
    setBase(base.filter((selected) => selected !== number));
    setAssociates([...associates, number]);
  }

  function useSuggestedBase() {
    setCustomError("");
    setCustomPlan(null);
    setBase(suggestedBase);
    setAssociates(associates.filter((number) => !suggestedBase.includes(number)));
  }

  function clearSelection() {
    setCustomError("");
    setCustomPlan(null);
    setBase([]);
    setAssociates([]);
  }

  function changeGame(size: number) {
    if (size === combinationSize) return;
    setCombinationSize(size);
    setAutoError("");
    setAutoPlan(null);
    setCustomError("");
    setCustomPlan(null);
    setBase((current) => current.slice(0, size - 1));
  }

  async function generateCustom() {
    setCustomError("");
    setCustomPlan(null);
    if (!online) {
      setCustomError(t.offline);
      return;
    }
    if (base.length === 0) {
      setCustomError(t.validationBase);
      return;
    }
    const needed = combinationSize - base.length;
    if (associates.length > 0 && associates.length < needed) {
      setCustomError(interpolate(t.validationAssociates, { count: needed }));
      return;
    }
    setCustomLoading(true);
    try {
      setCustomPlan(await requestPlan("/combinations/custom", { base, associates, combination_size: combinationSize }));
    } catch (error) {
      setCustomError(error instanceof Error && error.message ? error.message : t.error);
    } finally {
      setCustomLoading(false);
    }
  }

  async function savePlan(plan: CombinationPlan) {
    setSavedError("");
    setSavedMessage("");
    if (!saveName.trim()) {
      setSavedError(t.savedNameRequired);
      return;
    }
    setSavingPlan(true);
    try {
      const response = await apiFetch(`${apiUrl}/api/v1/races/${analysis.race_id}/combinations/saved`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: saveName.trim(),
          plan: {
            race_type: plan.race_type,
            combination_size: plan.combination_size,
            ready_tickets: plan.ready_tickets ?? [],
            base: plan.base,
            substitutes: plan.substitutes ?? [],
            combinations: plan.combinations,
          },
        }),
        cache: "no-store",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || !payload.saved_combination) {
        throw new Error(typeof payload.detail === "string" && payload.detail ? payload.detail : t.savedError);
      }
      setSavedPlans((current) => [payload.saved_combination, ...current]);
      setSavedMessage(t.savedConfirmation);
      setSaveName("");
    } catch (error) {
      setSavedError(error instanceof Error && error.message ? error.message : t.savedError);
    } finally {
      setSavingPlan(false);
    }
  }

  async function deleteSavedPlan(saved: SavedCombination) {
    setSavedError("");
    setSavedMessage("");
    try {
      const response = await apiFetch(
        `${apiUrl}/api/v1/races/${analysis.race_id}/combinations/saved/${saved.id}`,
        { method: "DELETE", cache: "no-store" },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" && payload.detail ? payload.detail : t.savedError);
      }
      setSavedPlans((current) => current.filter(({ id }) => id !== saved.id));
    } catch (error) {
      setSavedError(error instanceof Error && error.message ? error.message : t.savedError);
    }
  }

  function printPlan(target: string) {
    setPrintingTarget(target);
    window.setTimeout(() => window.print(), 50);
  }

  const selectionSummary = [
    base.length > 0
      ? interpolate(t.baseSummary, { numbers: base.join(" · ") })
      : t.baseEmpty,
    associates.length > 0
      ? interpolate(t.associatesSummary, { numbers: associates.join(" · ") })
      : t.associatesEmpty,
  ].join(" — ");

  return (
    <section className="subscriber-combinations" aria-labelledby="subscriber-combinations-title">
      <div className="subscriber-section-heading">
        <div>
          <p className="public-kicker">{t.kicker}</p>
          <h2 id="subscriber-combinations-title">{t.title}</h2>
          <p>{t.description}</p>
        </div>
      </div>

      <div className="combination-game-switch" role="group" aria-label={t.gameAria}>
        {GAME_OPTIONS.map((option) => (
          <button
            key={option.size}
            type="button"
            aria-pressed={combinationSize === option.size}
            onClick={() => changeGame(option.size)}
          >
            {t[option.label]}
          </button>
        ))}
      </div>

      <div className="saved-combinations-controls">
        <label htmlFor="saved-combination-name">{t.savedNameLabel}</label>
        <input
          id="saved-combination-name"
          value={saveName}
          onChange={(event) => setSaveName(event.target.value)}
          maxLength={80}
          placeholder={t.savedNamePlaceholder}
        />
      </div>
      {savedError && <p className="error" role="alert">{savedError}</p>}
      {savedMessage && <p className="free-analysis-status" role="status">{savedMessage}</p>}
      {savedLoading && <p className="muted-result">{t.savedLoading}</p>}

      <article
        className={`combination-panel public-widget${printingTarget === "auto" ? " combination-print-target" : ""}`}
      >
        <div className="combination-panel-heading">
          <div>
            <h3>{t.autoTitle}</h3>
            <p>{interpolate(t.autoDescription, { size: combinationSize, count: maxTickets })}</p>
          </div>
          <button
            type="button"
            className="subscriber-refresh"
            onClick={() => void loadAutoPlan()}
            disabled={autoLoading || !online}
          >
            {autoLoading ? t.generating : autoPlan ? t.autoRefresh : t.autoCta}
          </button>
        </div>
        {autoError && <p className="error" role="alert">{autoError}</p>}
        {autoPlan ? (
          <CombinationResults
            plan={autoPlan}
            onSave={() => void savePlan(autoPlan)}
            onPrint={() => printPlan("auto")}
            saving={savingPlan}
            saveDisabled={!online}
          />
        ) : <p className="muted-result">{t.none}</p>}
      </article>

      <article
        className={`combination-panel public-widget${printingTarget === "custom" ? " combination-print-target" : ""}`}
      >
        <div className="combination-panel-heading">
          <div>
            <h3>{t.customTitle}</h3>
            <p>{interpolate(t.customDescription, { size: combinationSize })}</p>
          </div>
          <div className="combination-panel-actions">
            <button type="button" className="cache-refresh-button" onClick={useSuggestedBase} disabled={suggestedBase.length === 0}>
              {t.useSuggested}
            </button>
            <button type="button" className="cache-refresh-button" onClick={clearSelection} disabled={base.length === 0 && associates.length === 0}>
              {t.clear}
            </button>
          </div>
        </div>
        <p className="muted-result">{selectionSummary}</p>
        <div className="combination-picker">
          {starters.map(({ number, name, score }) => {
            const isBase = base.includes(number);
            const isAssociate = associates.includes(number);
            return (
              <div
                className={`combination-pick${isBase ? " base-pick" : ""}${isAssociate ? " associate-pick" : ""}`}
                key={number}
              >
                <strong>{number}</strong>
                <span>{name || messages.recommendations.unknownHorse}</span>
                <b>{score === null ? "—" : score.toLocaleString(intlLocale, { maximumFractionDigits: 2 })}</b>
                <div className="combination-pick-actions">
                  <button
                    type="button"
                    aria-pressed={isBase}
                    aria-label={interpolate(t.pickBaseAria, { number })}
                    onClick={() => toggleBase(number)}
                  >
                    {t.pickBase}
                  </button>
                  <button
                    type="button"
                    aria-pressed={isAssociate}
                    aria-label={interpolate(t.pickAssociateAria, { number })}
                    onClick={() => toggleAssociate(number)}
                  >
                    {t.pickAssociate}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <p className="muted-result">
          {interpolate(t.baseHint, { maxBase, size: combinationSize })} {t.associatesHint}
          {plotTwistNumbers.length > 0 && <> {interpolate(t.plotTwistHint, { numbers: plotTwistNumbers.join(" · ") })}.</>}
        </p>
        {customError && <p className="error" role="alert">{customError}</p>}
        <button
          type="button"
          className="subscriber-refresh subscriber-combinations-cta"
          onClick={() => void generateCustom()}
          disabled={customLoading || !online}
        >
          {customLoading ? t.generating : t.generateCustom}
        </button>
        {customPlan && (
          <CombinationResults
            plan={customPlan}
            onSave={() => void savePlan(customPlan)}
            onPrint={() => printPlan("custom")}
            saving={savingPlan}
            saveDisabled={!online}
          />
        )}
      </article>
      {savedPlans.map((saved) => (
        <article
          className={`combination-panel public-widget saved-combination-card${printingTarget === saved.id ? " combination-print-target" : ""}`}
          key={saved.id}
        >
          <div className="combination-panel-heading">
            <div>
              <h3>{saved.name}</h3>
              <p>{new Date(saved.created_at).toLocaleString(intlLocale)}</p>
            </div>
            <div className="combination-panel-actions">
              <button type="button" className="cache-refresh-button" onClick={() => printPlan(saved.id)}>{t.print}</button>
              <button type="button" className="cache-refresh-button" onClick={() => void deleteSavedPlan(saved)}>{t.deleteSaved}</button>
            </div>
          </div>
          <CombinationResults plan={saved.plan} threeColumns />
        </article>
      ))}
      {savedPlans.length === 0 && !savedError && !savedLoading && <p className="muted-result">{t.savedEmpty}</p>}
    </section>
  );
}

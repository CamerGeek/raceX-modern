"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import SiteNavigation from "../site-navigation";

type Horse = Record<string, string | number | boolean | null>;
type AnalysisSection = { title: string; columns: string[]; rows: Horse[] };
type ModelPredictions = { status: "ready" | "unsupported" | "unavailable"; model_version: string | null; bet_list: number[]; rows: Horse[]; message: string | null };
type SimulationRow = Horse & { win_probability: number; podium_probability: number; average_simulated_rank: number };
type FlatOverview = { prognosis: Horse[]; summary: Horse[]; upset_potential: Horse[]; consistency_score: Horse[]; odds_divergence: Horse[]; best_starting_posts: string[]; track: string; distance: number; race_details: string };

type Analysis = {
  race_id?: string;
  row_count: number;
  race_type: "flat" | "trot";
  source: string;
  columns: string[];
  rows: Horse[];
  model_version: string;
  prognosis: Horse[];
  model_check?: Horse[] | null;
  handicap: { distance: number | null; penalized_count: number } | null;
  signals?: { label: string; value: string; detail: string }[];
  sections?: AnalysisSection[];
  overview?: FlatOverview;
  race_details: string;
  model_predictions?: ModelPredictions | null;
};

type ScrapeResult = {
  race_type: "flat" | "trot";
  runner_table: string;
  race_count: number;
  runner_count: number;
  columns: string[];
  races?: RaceOption[];
  already_stored?: boolean;
};

type RaceOption = { id: string; race_key: string; url: string; race_type?: "flat" | "trot"; q_plus?: boolean };

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchMeetings(date: string) {
  const response = await fetch(`${apiUrl}/api/v1/meetings?date=${date}&refresh=true`);
  if (!response.ok) throw new Error("Unable to load meetings");
  return response.json() as Promise<{ meetings: Record<string, string> }>;
}

function field(row: Horse, names: string[], fallback = "-") {
  const key = names.find((name) => row[name] !== undefined && row[name] !== null && row[name] !== "");
  return key ? String(row[key]) : fallback;
}

function numberField(row: Horse, names: string[]) {
  const value = Number(field(row, names, "0").replace(",", "."));
  return Number.isFinite(value) ? value : 0;
}

function averageField(rows: Horse[], names: string[]) {
  const values = rows.map((row) => numberField(row, names)).filter((value) => value > 0);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function formatValue(value: Horse[string]) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function deepScore(row: Horse) {
  return numberField(row, ["place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score"]);
}

function horseNumbers(rows: Horse[]) {
  return rows.map((row) => field(row, ["N°", "N", "Numero"], "-")).filter((number) => number !== "-");
}

function sectionRows(analysis: Analysis, title: string) {
  return analysis.sections?.find((section) => section.title === title)?.rows ?? [];
}

function modelCheckFromVisibleRankings(analysis: Analysis): Horse[] | null {
  const modelRows = analysis.model_predictions?.rows ?? [];
  if (analysis.model_predictions?.status !== "ready" || !modelRows.length || !analysis.rows.length) return null;

  const numberFrom = (row: Horse) => {
    const value = field(row, ["N°", "N", "Numero", "NUMERO", "N?", "NUM"], "");
    return value.trim().replace(/\.0$/, "");
  };
  const scoreFrom = (row: Horse, names: string[]) => {
    const raw = field(row, names, "").trim().replace(",", ".");
    if (!raw) return null;
    const score = Number(raw);
    return Number.isFinite(score) ? score : null;
  };
  const deepRows = modelRows
    .map((row) => ({ row, number: numberFrom(row), score: scoreFrom(row, ["place_prob_deep", "DEEP_SCORE", "Deep score", "Deep Score"]) }))
    .filter((item): item is { row: Horse; number: string; score: number } => Boolean(item.number) && item.score !== null)
    .sort((left, right) => right.score - left.score)
    .slice(0, Math.min(8, analysis.row_count));

  const compositeByNumber = new Map<string, { row: Horse; score: number }>();
  for (const row of [...analysis.rows, ...analysis.prognosis]) {
    const number = numberFrom(row);
    const score = scoreFrom(row, ["Composite", "COMPOSITE_SCORE", "SCORE", "CS_norm", "Score"]);
    if (number && score !== null) compositeByNumber.set(number, { row, score });
  }
  const compositeTop = [...compositeByNumber.entries()]
    .sort((left, right) => right[1].score - left[1].score)
    .slice(0, Math.min(8, analysis.row_count));
  if (!deepRows.length || !compositeTop.length) return null;

  const candidates = new Map<string, Horse>();
  const memberships = new Map<string, Set<string>>();
  const add = (number: string, row: Horse, source: string) => {
    candidates.set(number, { ...(candidates.get(number) ?? {}), ...row });
    const sources = memberships.get(number) ?? new Set<string>();
    sources.add(source);
    memberships.set(number, sources);
  };
  for (const row of analysis.prognosis) {
    const number = numberFrom(row);
    if (number) add(number, row, "Prognosis");
  }
  for (const { row, number } of deepRows) add(number, row, "Deep score top 8");
  for (const [number, { row }] of compositeTop) add(number, row, "Composite top 8");

  const sources = ["Prognosis", "Deep score top 8", "Composite top 8"];
  return [...candidates.entries()]
    .filter(([number]) => (memberships.get(number)?.size ?? 0) < sources.length)
    .map(([number, row]) => ({
      ...row,
      missing_from: sources.filter((source) => !memberships.get(number)?.has(source)).join(", "),
    }));
}

export default function AdminPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [url, setUrl] = useState("");
  const [meetingUrl, setMeetingUrl] = useState("");
  const [races, setRaces] = useState<RaceOption[]>([]);
  const [selectedRace, setSelectedRace] = useState("");
  const [storedMeeting, setStoredMeeting] = useState<boolean | null>(null);
  const [forceRefresh, setForceRefresh] = useState(false);
  const [selectionExpanded, setSelectionExpanded] = useState(true);
  const [meetingDate, setMeetingDate] = useState(today);
  const [meetings, setMeetings] = useState<Record<string, string>>({});
  const [meetingsLoading, setMeetingsLoading] = useState(true);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [showManualUrl, setShowManualUrl] = useState(false);
  const [raceType, setRaceType] = useState<"flat" | "trot">("trot");
  const [typeSource, setTypeSource] = useState<"automatic" | "manual">("automatic");
  const [detectingType, setDetectingType] = useState(false);
  const [includeHandicap, setIncludeHandicap] = useState(true);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [scrapeResult, setScrapeResult] = useState<ScrapeResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reportTab, setReportTab] = useState("overview");
  const [simulationRows, setSimulationRows] = useState<SimulationRow[]>([]);
  const [combinations, setCombinations] = useState<string[][]>([]);
  const [bettingLoading, setBettingLoading] = useState(false);
  const [bettingError, setBettingError] = useState("");

  const rankedHorses = analysis?.prognosis.length ? analysis.prognosis : analysis?.rows ?? [];
  const modelShortlistRows = [...(analysis?.model_predictions?.rows ?? [])]
    .sort((a, b) => deepScore(b) - deepScore(a));
  const modelOverviewRows = modelShortlistRows.slice(0, 8);
  const modelCheck = analysis
    ? analysis.model_check ?? modelCheckFromVisibleRankings(analysis)
    : null;
  const topHorse = rankedHorses[0];
  const topScore = topHorse ? numberField(topHorse, ["SCORE", "COMPOSITE_SCORE", "Composite", "Score"]) : 0;
  const topOdds = topHorse ? field(topHorse, ["COTE", "Cote", "Odds"]) : "-";
  const selectedMeetingLabel = Object.entries(meetings).find(([, meeting]) => meeting === meetingUrl)?.[0] ?? "Selected meeting";
  const selectedRaceLabel = races.find((race) => race.id === selectedRace)?.race_key ?? "Race report";

  useEffect(() => {
    let cancelled = false;
    fetchMeetings(meetingDate)
      .then((payload) => {
        if (!cancelled) setMeetings(payload.meetings ?? {});
      })
      .catch(() => {
        if (!cancelled) {
          setMeetings({});
          setError("Unable to load meetings. Check the backend URL and CORS settings.");
        }
      })
      .finally(() => {
        if (!cancelled) setMeetingsLoading(false);
      });
    return () => { cancelled = true; };
  }, [meetingDate]);

  async function loadMeetings() {
    setMeetingsLoading(true);
    setError("");
    try {
      const payload = await fetchMeetings(meetingDate);
      setMeetings(payload.meetings ?? {});
    } catch (requestError) {
      setMeetings({});
      setError(requestError instanceof Error ? requestError.message : "Unable to load meetings");
    } finally {
      setMeetingsLoading(false);
    }
  }

  async function refreshTurfomaniaCatalog() {
    setCatalogLoading(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/turfomania/reunions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: meetingDate }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Unable to refresh the Turfomania catalog");
      await loadMeetings();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to refresh the Turfomania catalog");
    } finally {
      setCatalogLoading(false);
    }
  }

  useEffect(() => {
    if (!url || showManualUrl) return;
    const isTurfomaniaRaceUrl = meetingUrl.startsWith("turfomania://") && url !== meetingUrl;
    if (isTurfomaniaRaceUrl) return;
    let cancelled = false;
    fetch(`${apiUrl}/api/v1/races/detect-type?url=${encodeURIComponent(url)}`)
      .then(async (response) => {
        if (!response.ok) throw new Error("Race type detection failed");
        return response.json() as Promise<{ race_type: "flat" | "trot" }>;
      })
      .then((payload) => {
        if (!cancelled) { setRaceType(payload.race_type); setTypeSource("automatic"); }
      })
      .catch(() => { if (!cancelled) setTypeSource("manual"); })
      .finally(() => { if (!cancelled) setDetectingType(false); });
    return () => { cancelled = true; };
  }, [url, showManualUrl, meetingUrl]);

  function selectMeeting(nextUrl: string) {
    setMeetingUrl(nextUrl);
    setUrl(nextUrl);
    setSelectionExpanded(true);
    setRaces([]);
    setSelectedRace("");
    setStoredMeeting(null);
    setDetectingType(Boolean(nextUrl));
    setAnalysis(null);
    setScrapeResult(null);
    setError("");
    setShowManualUrl(false);
    setTypeSource("automatic");
    if (nextUrl) {
      fetch(`${apiUrl}/api/v1/meetings/stored?meeting_url=${encodeURIComponent(nextUrl)}&date=${encodeURIComponent(meetingDate)}`)
        .then(async (response) => {
          if (!response.ok) throw new Error("Stored meeting check failed");
          return response.json() as Promise<{ exists: boolean; races: RaceOption[] }>;
        })
        .then((payload) => {
          setStoredMeeting(payload.exists);
          setRaces(payload.races ?? []);
        })
        .catch(() => setStoredMeeting(false));
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setAnalysis(null);
    setScrapeResult(null);

    try {
      const effectiveUrl = meetingUrl || url;
      const source = effectiveUrl.startsWith("turfomania://") ? "turfomania" : "zone-turf";
      const response = await fetch(`${apiUrl}/api/v1/meetings/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: meetingDate,
          meeting_url: effectiveUrl,
          race_type: raceType,
          source,
          force_refresh: forceRefresh,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Meeting scrape failed");
      setScrapeResult(payload);
      setStoredMeeting(true);
      setRaces(payload.races ?? []);
      setForceRefresh(false);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Meeting scrape failed");
    } finally {
      setLoading(false);
    }
  }

  async function analyzeSelectedRace(race: RaceOption | undefined = races.find((race) => race.id === selectedRace)) {
    if (!race) return;
    setLoading(true);
    setError("");
    setAnalysis(null);
    setScrapeResult(null);
    try {
      const source = meetingUrl.startsWith("turfomania://") ? "turfomania" : "zone-turf";
      const response = await fetch(`${apiUrl}/api/v1/races/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: race.url, race_id: race.id, race_type: race.race_type ?? raceType, source, include_handicap: includeHandicap, max_horses: 8 }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Race analysis failed");
      setUrl(race.url);
      setAnalysis(payload as Analysis);
      setSelectionExpanded(false);
      setReportTab("overview");
      setSimulationRows([]);
      setCombinations([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Race analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function analyzeTurfomaniaQuinte() {
    const prefix = "turfomania://meetings/";
    if (!meetingUrl.startsWith(prefix)) return;
    setLoading(true);
    setError("");
    setAnalysis(null);
    setScrapeResult(null);
    try {
      const response = await fetch(`${apiUrl}/api/v1/races/turfomania/quinte/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          meeting_id: meetingUrl.slice(prefix.length),
          include_handicap: includeHandicap,
          max_horses: 8,
        }),
      });
      const payload = await response.json() as Analysis;
      if (!response.ok) throw new Error((payload as Analysis & { detail?: string }).detail ?? "Quinté+ analysis failed");
      const race: RaceOption = {
        id: payload.race_id ?? "",
        race_key: field(payload.rows[0] ?? {}, ["REF_COURSE"], "Q+"),
        url: "https://www.turfomania.fr/quinte/",
        race_type: payload.race_type,
        q_plus: true,
      };
      if (race.id) {
        setRaces((previous) => [...previous.filter((item) => item.id !== race.id), race]);
        setSelectedRace(race.id);
      }
      setUrl(race.url);
      setRaceType(payload.race_type);
      setTypeSource("automatic");
      setAnalysis(payload);
      setSelectionExpanded(false);
      setReportTab("overview");
      setSimulationRows([]);
      setCombinations([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Quinté+ analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadBettingTab(tab: "simulation" | "combinations") {
    const race = races.find((item) => item.id === selectedRace);
    if (!race) return;
    setReportTab(tab);
    setBettingLoading(true);
    setBettingError("");
    try {
      const endpoint = tab === "simulation" ? "simulate" : "combinations";
      const body = tab === "simulation"
        ? { race_id: race.id, race_type: race.race_type ?? raceType, simulations: 5000 }
        : { race_id: race.id, race_type: race.race_type ?? raceType, combination_size: 5, max_combinations: 50, mandatory: [], excluded: [] };
      const response = await fetch(`${apiUrl}/api/v1/races/${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `${tab} failed`);
      if (tab === "simulation") setSimulationRows(payload.rows ?? []);
      else setCombinations(payload.combinations ?? []);
    } catch (requestError) {
      setBettingError(requestError instanceof Error ? requestError.message : `${tab} failed`);
    } finally {
      setBettingLoading(false);
    }
  }

  return (
    <main className="shell">
      <SiteNavigation currentPage="analysis" />
      <header className="masthead">
        <div className="brand-line">
          <Image src="/racex-logo.png" alt="RaceX logo" width={540} height={180} priority className="brand-logo" />
          <span className="status-dot">LIVE MODEL</span>
        </div>
        <div className="masthead-copy">
          <div className="masthead-kicker">PRECISION RACING INTELLIGENCE</div>
          <h1>Read the race <em>before</em> it runs.</h1>
          <p>Turn the race card into a calm, evidence-led shortlist. Start with the source URL, then inspect the signal behind every selection.</p>
        </div>
      </header>

      <section className="workspace" aria-label="Race analysis workspace">
        <form className={`control-panel${analysis ? " has-analysis" : ""}${selectionExpanded ? " selection-expanded" : ""}`} onSubmit={submit}>
          {analysis && <div className="mobile-selection-summary">
            <div><span>ANALYZING</span><strong>{selectedMeetingLabel} · {selectedRaceLabel}</strong></div>
            <button type="button" aria-expanded={selectionExpanded} aria-controls="race-selection-controls" onClick={() => setSelectionExpanded((expanded) => !expanded)}>{selectionExpanded ? "Done" : "Change race"}</button>
          </div>}
          <div className="selection-controls" id="race-selection-controls">
          <div className="form-heading"><div><div className="eyebrow">01 / SELECT A PROGRAM</div><h3>Find today&apos;s races</h3></div><span className="live-label">ZONE-TURF + TURFOMANIA</span></div>
          <label htmlFor="meeting-date">Meeting date</label>
          <input id="meeting-date" type="date" value={meetingDate} onChange={(event) => { setMeetingsLoading(true); setMeetingDate(event.target.value); }} />
          <button type="button" className="load-meetings-button" onClick={loadMeetings} disabled={meetingsLoading || catalogLoading}><span aria-hidden="true">↻</span>{meetingsLoading ? "Loading meetings..." : "Load Meetings"}</button>
          <button type="button" className="catalog-button" onClick={refreshTurfomaniaCatalog} disabled={meetingsLoading || catalogLoading}><span aria-hidden="true">↻</span>{catalogLoading ? "Refreshing Turfomania..." : "Refresh Turfomania catalog"}</button>
          <label htmlFor="meeting-select">Available meetings</label>
          <select id="meeting-select" value={url} onChange={(event) => selectMeeting(event.target.value)} disabled={meetingsLoading || Object.keys(meetings).length === 0}>
            <option value="">{meetingsLoading ? "Loading meetings..." : Object.keys(meetings).length ? "Choose a meeting" : "No meetings found for this date"}</option>
            {Object.entries(meetings).map(([label, meetingUrl]) => <option value={meetingUrl} key={meetingUrl}>{label}</option>)}
          </select>
          {storedMeeting && <p className="stored-notice" role="status">Already saved. Choose a race below, or enable fresh download.</p>}
          {races.length > 0 && <>
            <label htmlFor="race-select">Races in meeting</label>
            <select id="race-select" value={selectedRace} onChange={(event) => {
              const next = races.find((race) => race.id === event.target.value);
              setSelectedRace(event.target.value);
              setUrl(next?.url ?? meetingUrl);
              setAnalysis(null);
              setScrapeResult(null);
              if (next) void analyzeSelectedRace(next);
            }}>
              <option value="">Choose a REF_COURSE</option>
              {races.map((race) => <option value={race.id} key={race.id}>{race.race_key}{race.q_plus ? " · Q+" : ""}</option>)}
            </select>
          </>}
          {storedMeeting && <label className="toggle"><input type="checkbox" checked={forceRefresh} onChange={(event) => setForceRefresh(event.target.checked)} /><span>Download meeting again</span></label>}
          <button type="button" className="manual-toggle" onClick={() => setShowManualUrl((visible) => !visible)}>{showManualUrl ? "Use meeting picker" : "Enter a race URL manually"}<span>↗</span></button>
          {showManualUrl && <><label htmlFor="race-url">Race URL</label><input id="race-url" type="url" required value={url} onChange={(event) => { setUrl(event.target.value); setTypeSource("automatic"); }} placeholder="https://www.zone-turf.fr/..." /></>}

          <div className="control-row">
            <div>
              <div className="type-label"><span className="label">Discipline</span><span className={typeSource === "automatic" ? "auto-badge" : "manual-badge"}>{detectingType ? "Detecting..." : typeSource === "automatic" ? "Auto-detected" : "Manual override"}</span></div>
              <div className="segmented">
                <button type="button" className={raceType === "trot" ? "selected" : ""} onClick={() => { setRaceType("trot"); setTypeSource("manual"); }}>Trot</button>
                <button type="button" className={raceType === "flat" ? "selected" : ""} onClick={() => { setRaceType("flat"); setTypeSource("manual"); }}>Flat</button>
              </div>
            </div>
            <label className="toggle"><input type="checkbox" checked={includeHandicap} onChange={(event) => setIncludeHandicap(event.target.checked)} /><span>Handicap mechanics</span></label>
          </div>

          <button className="analyze-button" type="submit" disabled={loading || detectingType || !meetingUrl && !url}>{loading ? "Saving meeting..." : storedMeeting && !forceRefresh ? "Load saved meeting" : "Download & save meeting"}<span aria-hidden="true">↗</span></button>
          {selectedRace && <button className="analyze-button" type="button" onClick={() => void analyzeSelectedRace()} disabled={loading || detectingType}>{loading ? "Analyzing race..." : "Re-run analysis"}<span aria-hidden="true">↗</span></button>}
          {meetingUrl.startsWith("turfomania://meetings/") && !showManualUrl && <>
            <button className="analyze-button quinte-button" type="button" onClick={() => void analyzeTurfomaniaQuinte()} disabled={loading || meetingDate !== today}>
              {loading ? "Scraping & analyzing Quinté+..." : "Scrape & analyze today’s Quinté+"}<span aria-hidden="true">↗</span>
            </button>
            {meetingDate !== today && <p className="stored-notice">The generic Turfomania Quinté page only provides the current day’s race.</p>}
          </>}
          {error && <p className="error" role="alert">{error}</p>}
          </div>
        </form>

        <section className="results-panel" aria-live="polite">
          <div className="section-heading"><div><div className="eyebrow">PROGNOSIS / {analysis ? analysis.race_type.toUpperCase() : "WAITING"}</div><h2>{analysis ? "Race report" : "Short list"}</h2></div>{analysis && <span className="count">{analysis.row_count} runners read</span>}</div>
          {!analysis && !scrapeResult && !loading && <div className="empty-state"><span className="starting-mark">01</span><p>Select a date and meeting to begin.</p></div>}
          {loading && <div className="empty-state"><span className="starting-mark pulse">...</span><p>Scraping and preparing the race report.</p></div>}
          {scrapeResult && <div className="saved-state"><span className="starting-mark">✓</span><h3>Meeting saved</h3><p>{scrapeResult.race_count} races and {scrapeResult.runner_count} runners stored in <strong>{scrapeResult.runner_table}</strong>.</p><span>{scrapeResult.columns.length} source columns preserved</span></div>}
          {analysis && <>
            {analysis.race_details && <div className="race-details"><span>RACE DETAILS</span><p>{analysis.race_details}</p></div>}
            <section className="prognosis-miss-signal" aria-label="Horses not shared by prognosis, deep-score top eight, and composite top eight">
              <div className="prognosis-miss-heading">
                <span>MODEL CHECK</span>
                <h3>Horses not shared across Prognosis, deep-score, and composite</h3>
                <p>Deep-score and composite rankings include up to the top 8 starters.</p>
              </div>
              {modelCheck === null
                ? <p className="prognosis-miss-empty">Comparison unavailable: deep-score or composite ranking is missing.</p>
                : modelCheck.length
                  ? <ul>{modelCheck.map((horse, index) => {
                    const number = field(horse, ["N°", "N", "Numero", "N?", "NUMERO"], String(index + 1));
                    return <li key={`${number}-${index}`}><strong>{number}</strong></li>;
                  })}</ul>
                  : <p className="prognosis-miss-empty">None in this prognosis</p>}
            </section>
            {analysis.race_type === "flat" && analysis.overview && <div className="quick-feel-grid">
              <div className="quick-feel-card"><span>PROGNOSIS</span><strong>{horseNumbers(analysis.overview.prognosis).join(" · ") || "-"}</strong></div>
              <div className="quick-feel-card"><span>SUMMARY</span><strong>{horseNumbers(analysis.overview.summary).join(" · ") || "-"}</strong></div>
              <div className="quick-feel-card"><span>POTENTIAL UPSETS</span><strong>{horseNumbers(analysis.overview.upset_potential).join(" · ") || "-"}</strong></div>
              <div className="quick-feel-card"><span>BEST STARTING POSTS</span><strong>{analysis.overview.best_starting_posts.join(" · ") || "-"}</strong></div>
            </div>}
            <div className="race-meta"><span>{analysis.source}</span><span>Model {analysis.model_version}</span><a href={url} target="_blank" rel="noreferrer">Open source race ↗</a></div>
            <div className="report-tab-navigation">
            <nav className="report-tabs" role="tablist" aria-label="Race report sections">
              {[{ id: "overview", label: "Overview" }, { id: "model", label: "Model" }, { id: "composite", label: "Composite" }, { id: "simulation", label: "Monte Carlo" }, { id: "combinations", label: "Combinations" }, { id: "data", label: `Full data (${analysis.columns.length})` }].map((tab) => <button type="button" role="tab" className={reportTab === tab.id ? "active" : ""} aria-selected={reportTab === tab.id} key={tab.id} onClick={() => tab.id === "simulation" || tab.id === "combinations" ? void loadBettingTab(tab.id) : setReportTab(tab.id)}>{tab.label}</button>)}
            </nav>
            <span className="report-tabs-hint" aria-hidden="true">Swipe for sections <span>→</span></span>
            </div>
            {reportTab === "overview" && <>
            {topHorse && <div className="hero-selection">
              <div><span className="hero-kicker">TOP SELECTION</span><h3>{field(topHorse, ["CHEVAL", "Cheval", "HORSE"], "Unknown horse")}</h3><p>Highest composite signal in this field</p></div>
              <div className="hero-stats"><div><span>Score</span><strong>{topScore.toFixed(2)}</strong></div><div><span>Odds</span><strong>{topOdds}</strong></div></div>
            </div>}
            <div className="metric-strip"><div><span>FIELD</span><strong>{analysis.row_count}</strong><small>runners read</small></div><div><span>MODEL</span><strong>{analysis.model_version}</strong><small>scoring profile</small></div><div><span>HANDICAP</span><strong>{analysis.handicap?.distance ? `${analysis.handicap.distance}m` : "Open"}</strong><small>{analysis.handicap ? `${analysis.handicap.penalized_count} marked` : "No adjustment"}</small></div></div>
            {analysis.race_type === "trot" && <div className="metric-strip trot-signals"><div><span>AVG S_COEFF</span><strong>{averageField(analysis.rows, ["S_COEFF"]).toFixed(2)}</strong><small>recent performance</small></div><div><span>AVG IF</span><strong>{averageField(analysis.rows, ["IF", "FA", "FM"]).toFixed(2)}</strong><small>fitness index</small></div><div><span>AVG DQ RISK</span><strong>{averageField(analysis.rows, ["DQ_Risk"]).toFixed(1)}</strong><small>disqualification signal</small></div></div>}
            {analysis.race_type === "trot" && <div className="overview-grid trot-overview-grid">
              <div className="overview-card"><h3>Trot prognosis</h3><p>Weighted multi-signal ranking</p><ol>{analysis.prognosis.slice(0, 8).map((horse, index) => <li key={`trot-prognosis-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["CHEVAL", "Cheval"], "Unknown")}</span><b>{formatValue(horse.Composite)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Performance</h3><p>Success coefficient ranking</p><ol>{sectionRows(analysis, "Performance (S_COEFF)").slice(0, 8).map((horse, index) => <li key={`trot-performance-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["Cheval", "CHEVAL"], "Unknown")}</span><b>{formatValue(horse.S_COEFF_Handicap_Adj ?? horse.S_COEFF)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Disqualification risk</h3><p>Highest risk signals first</p><ol>{sectionRows(analysis, "Disqualification Risk").slice(0, 8).map((horse, index) => <li key={`trot-dq-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["Cheval", "CHEVAL"], "Unknown")}</span><b>{formatValue(horse.DQ_Risk_Amplified ?? horse.DQ_Risk)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Form and shoeing</h3><p>Recent trajectory and equipment</p><ol>{sectionRows(analysis, "Form Trend").slice(0, 8).map((horse, index) => <li key={`trot-form-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["Cheval", "CHEVAL"], "Unknown")}</span><b>{field(horse, ["Trend"], "-")}</b></li>)}</ol></div>
            </div>}
            {analysis.race_type === "flat" && analysis.overview && <div className="overview-grid">
              <div className="overview-card"><h3>Prognosis</h3><p>Legacy-ranked candidates</p><ol>{analysis.overview.prognosis.map((horse, index) => <li key={`prognosis-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["CHEVAL", "Cheval"], "Unknown")}</span><b>{formatValue(horse.Composite)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Composite summary</h3><p>Top 8 horses in score order</p><ol>{analysis.overview.summary.map((horse, index) => <li key={`summary-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["CHEVAL", "Cheval"], "Unknown")}</span><b>{formatValue(horse.Composite)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Upset potential</h3><p>Legacy consistency signals</p><ol>{analysis.overview.upset_potential.slice(0, 8).map((horse, index) => <li key={`upset-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["CHEVAL", "Cheval"], "Unknown")}</span><b>{formatValue(horse.consistency_score ?? horse.Divergence ?? horse.FinalUpset)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Consistency score</h3><p>Legacy multi-factor consistency</p><ol>{analysis.overview.consistency_score.slice(0, 8).map((horse, index) => <li key={`consistency-${index}`}><strong>{field(horse, ["N°", "N", "Numero"])}</strong><span>{field(horse, ["Cheval", "CHEVAL"], "Unknown")}</span><b>{formatValue(horse.consistency_score)}</b></li>)}</ol></div>
              <div className="overview-card"><h3>Odds divergence</h3><p>Composite rank versus market rank</p><ol>{analysis.overview.odds_divergence.slice(0, 8).map((horse, index) => <li key={`divergence-${index}`}><strong>{field(horse, ["N", "N°", "Numero"])}</strong><span>{field(horse, ["Cheval", "CHEVAL"], "Unknown")}</span><b>{formatValue(horse.Divergence)}</b></li>)}</ol></div>
              <div className="overview-card starting-post-card"><h3>Best starting posts</h3><p>{analysis.overview.track || "Track unavailable"}{analysis.overview.distance ? ` / ${analysis.overview.distance}m` : ""}</p>{analysis.overview.best_starting_posts.length ? <div className="post-list">{analysis.overview.best_starting_posts.map((horseNumber) => <span key={horseNumber}>{horseNumber}</span>)}</div> : <strong className="muted-result">No track-specific post data</strong>}</div>
            </div>}
            {analysis.model_predictions && <div className="overview-grid"><article className="overview-card"><h3>Model shortlist</h3><p>Top 8 horses sorted by deep score</p>{analysis.model_predictions.status === "ready" ? <div className="post-list">{modelOverviewRows.map((horse, index) => <span key={`shortlist-${field(horse, ["NUMERO", "N°", "N"], String(index))}`}>{field(horse, ["NUMERO", "N°", "N"], String(index + 1))}</span>)}</div> : <strong className="muted-result">{analysis.model_predictions.message}</strong>}</article></div>}
            </>}
            {reportTab === "model" && analysis.model_predictions && <div className="report-section"><div className="section-title"><span>ML</span><h3>Model shortlist</h3><p>{analysis.model_predictions.status === "ready" ? `${modelShortlistRows.length} horses · sorted by deep score` : analysis.model_predictions.status}</p></div>{analysis.model_predictions.status === "ready" ? <><p className="muted-result">Class-balanced model scores are useful for ranking, not as calibrated probabilities. Model {analysis.model_predictions.model_version ?? "version unavailable"}.</p><div className="table-scroll-hint" aria-hidden="true">Swipe to see all columns <span>→</span></div><div className="table-wrap"><table><thead><tr><th>Rank</th><th>Horse</th><th>Place score</th><th>Deep score</th><th>Win score</th><th>Dark-horse score</th><th>Votes</th><th>Priority tier</th></tr></thead><tbody>{modelShortlistRows.map((horse, index) => <tr key={`model-${field(horse, ["NUMERO", "N°", "N"], String(index))}`}><td className="rank">{index + 1}</td><td>{field(horse, ["NUMERO", "N°", "N"], "-")} / {field(horse, ["CHEVAL", "Cheval"], "Unknown")}</td><td>{formatValue(horse.place_prob)}</td><td>{formatValue(horse.place_prob_deep)}</td><td>{formatValue(horse.p_win)}</td><td>{formatValue(horse.dark_prob)}</td><td>{formatValue(horse.votes)}</td><td>{formatValue(horse.bet_tier)}</td></tr>)}</tbody></table></div></> : <p className="muted-result">{analysis.model_predictions.message}</p>}</div>}
            {reportTab === "composite" && <>
            <div className="report-section"><div className="section-title"><span>01</span><h3>Composite ranking</h3><p>Score and market odds at a glance</p></div><div className="ranking-grid">{(() => { const displayedHorses = rankedHorses.slice(0, 16); const maxOdds = Math.max(...displayedHorses.map((item) => numberField(item, ["COTE", "Cote", "Odds"])), 1); return displayedHorses.map((horse, index) => {
              const score = numberField(horse, ["SCORE", "COMPOSITE_SCORE", "Composite", "Score"]);
              const odds = numberField(horse, ["COTE", "Cote", "Odds"]);
              return <article className={`horse-card ${index === 0 ? "top-1" : index < 3 ? "top-3" : ""}`} key={`${field(horse, ["CHEVAL", "Cheval", "HORSE"], String(index))}-${index}`}>
                <div className="horse-header"><span className="pos-badge">{String(index + 1).padStart(2, "0")}</span><span className="num-badge">{field(horse, ["NÂ°", "N°", "NUM", "N"], String(index + 1))}</span><strong>{field(horse, ["CHEVAL", "Cheval", "HORSE"], "Unknown")}</strong><b>{field(horse, ["COTE", "Cote", "Odds"])}</b></div>
                <div className="bar-row"><span>Score</span><div className="bar-track"><i className="bar-fill score-fill" style={{ width: `${Math.min(100, Math.max(0, score * 100))}%` }} /></div><small>{score.toFixed(2)}</small></div>
                <div className="bar-row"><span>Odds</span><div className="bar-track"><i className="bar-fill odds-fill" style={{ width: `${Math.min(100, Math.max(0, (odds / maxOdds) * 100))}%` }} /></div><small>{field(horse, ["COTE", "Cote", "Odds"])}</small></div>
              </article>;
            }); })()}</div></div>
            </>}
            {reportTab === "simulation" && <div className="report-section"><div className="section-title"><span>MC</span><h3>Monte Carlo simulation</h3><p>5,000 simulated race orders</p></div>{bettingLoading && <p className="muted-result">Running simulation...</p>}{bettingError && <p className="error">{bettingError}</p>}{!bettingLoading && !bettingError && <><div className="table-scroll-hint" aria-hidden="true">Swipe to see all columns <span>→</span></div><div className="table-wrap"><table><thead><tr><th>Horse</th><th>Win probability</th><th>Top-3 probability</th><th>Average rank</th></tr></thead><tbody>{simulationRows.slice(0, 16).map((horse, index) => <tr key={`sim-${index}`}><td>{field(horse, ["N°", "N"], "-")} / {field(horse, ["Cheval", "CHEVAL"], "Unknown")}</td><td>{(horse.win_probability * 100).toFixed(1)}%</td><td>{(horse.podium_probability * 100).toFixed(1)}%</td><td>{horse.average_simulated_rank.toFixed(2)}</td></tr>)}</tbody></table></div></>}</div>}
            {reportTab === "combinations" && <div className="report-section"><div className="section-title"><span>COMB</span><h3>Generated combinations</h3><p>{combinations.length} tickets / 5 horses</p></div>{bettingLoading && <p className="muted-result">Generating combinations...</p>}{bettingError && <p className="error">{bettingError}</p>}{!bettingLoading && !bettingError && <div className="combination-grid">{combinations.map((combination, index) => <div className="combination-row" key={`combo-${index}`}><strong>{String(index + 1).padStart(2, "0")}</strong>{combination.map((horse) => <span key={horse}>{horse}</span>)}</div>)}</div>}</div>}
            {reportTab === "overview" && <>
            <div className="report-section"><div className="section-title"><span>02</span><h3>Handicap mechanics</h3><p>Distance and penalty signals</p></div><div className="handicap-panel"><strong>{analysis.handicap?.distance ? `${analysis.handicap.distance}m handicap` : "No distance handicap detected"}</strong><span>{analysis.handicap ? `${analysis.handicap.penalized_count} runners carry a penalty` : "The field is compared without a distance adjustment."}</span></div></div>
            </>}
            {reportTab === "data" && <>
            <div className="report-section"><div className="section-title"><span>03</span><h3>Full race data</h3><p>{analysis.columns.length} source and computed fields</p></div><div className="table-scroll-hint" aria-hidden="true">Swipe to see all columns <span>→</span></div><div className="table-wrap"><table><thead><tr><th>#</th>{analysis.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{analysis.rows.map((row, index) => <tr key={`row-${index}`}><td className="rank">{index + 1}</td>{analysis.columns.map((column) => <td key={column}>{formatValue(row[column])}</td>)}</tr>)}</tbody></table></div></div>
            </>}
          </>}
        </section>
      </section>
    </main>
  );
}

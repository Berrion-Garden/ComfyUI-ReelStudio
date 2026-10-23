import { useEffect, useState } from "react";
import { fetchValidate, runValidate, type ReviewReport } from "../api";

const KINDS: { id: string; label: string }[] = [
  { id: "prompts", label: "Scene prompts vs narrative" },
  { id: "entities", label: "Characters & locations vs narrative" },
  { id: "frames", label: "Rendered frames vs narrative" },
];

/** One flagged row of a review: which scene/slug, which beat, why. */
interface Finding {
  item: string;
  beat?: string | null;
  verdict: string;
  note: string;
}

/**
 * The "Validate" tab in chat: tick the kinds of validation to run, and one
 * reviewer agent per kind kicks off — each reads the narrative against its
 * kind of production data (composed prompts, entity blocks, rendered
 * frames) and their findings are merged into one merged view below.
 */
export function ValidatePanel() {
  const [reports, setReports] = useState<Record<string, ReviewReport>>({});
  const [ticked, setTicked] = useState<Record<string, boolean>>(
    { prompts: true, entities: true, frames: false });
  const [starting, setStarting] = useState(false);

  const load = async () => {
    try {
      setReports((await fetchValidate()).reports);
    } catch { /* the poll retries — keep the last reports */ }
  };

  const anyRunning = Object.values(reports).some((r) => r.state === "running");
  useEffect(() => {
    void load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  const selected = KINDS.filter((k) => ticked[k.id]).map((k) => k.id);
  const totalIssues = Object.values(reports).reduce(
    (n, r) => n + (r.findings ?? []).filter((f) => f.verdict === "issue")
      .length, 0);
  const reviewed = Object.values(reports).reduce(
    (n, r) => n + (r.findings?.length ?? 0), 0);

  return (
    <div className="validate-panel">
      <div className="validate-kinds">
        {KINDS.map((k) => (
          <label key={k.id} className="validate-kind">
            <input type="checkbox" checked={!!ticked[k.id]}
              onChange={() => setTicked((t) => ({ ...t, [k.id]: !t[k.id] }))}
              disabled={anyRunning} />
            {k.label}
          </label>
        ))}
      </div>
      <button type="button" disabled={starting || anyRunning
        || selected.length === 0}
        onClick={async () => {
          setStarting(true);
          try { await runValidate(selected); await load(); }
          finally { setStarting(false); }
        }}>
        {anyRunning ? "Reviewing…" : `Run ${selected.length} review${
          selected.length === 1 ? "" : "s"}`}
      </button>
      {reviewed > 0 &&
        <p className="validate-summary">
          {totalIssues} issue{totalIssues === 1 ? "" : "s"} across {reviewed}{" "}
          reviewed rows
        </p>}
      {KINDS.map((k) => {
        const r = reports[k.id];
        if (!r || r.state === "idle") return null;
        const issues = (r.findings ?? []).filter(
          (f) => f.verdict === "issue").length;
        return (
          <section key={k.id} className="validate-section">
            <h6>{k.label}
              <span className={`validate-state ${r.state}`}>{r.state}</span>
            </h6>
            {r.state === "error" && <p className="validate-error">⚠ {r.error}</p>}
            {r.state === "running" &&
              <p className="validate-progress">
                {r.done}/{r.total} rows…</p>}
            {(r.findings ?? []).map((f: Finding) => (
              <div key={`${k.id}-${f.item}`} className={`finding ${f.verdict}`}>
                <b>{f.item}</b>
                {f.beat && <span className="beat-id">{f.beat}</span>}
                <span className="finding-note">{f.note}</span>
              </div>
            ))}
            {r.state === "done" && issues === 0 &&
              <p className="validate-ok">no issues flagged</p>}
          </section>
        );
      })}
    </div>
  );
}

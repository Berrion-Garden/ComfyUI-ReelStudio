import { useEffect, useState } from "react";
import { fetchValidate, runValidate } from "../api";

/** One flagged segment of the review: what the reviewer saw vs the beat. */
interface Finding {
  segment: string;
  beat: string | null;
  verdict: string;
  note: string;
}

interface Report {
  state: string;
  error?: string;
  total?: number;
  done?: number;
  findings?: Finding[];
}

/**
 * The "Validate" tab in chat: an LLM reads the narrative against the final
 * cut (one midpoint frame per rendered segment) and flags anything that
 * does not match. The report streams in through the polling — batches land
 * as the reviewer finishes them.
 */
export function ValidatePanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [starting, setStarting] = useState(false);

  const load = async () => {
    try {
      setReport((await fetchValidate()).report);
    } catch { /* the poll retries — keep the last report */ }
  };

  useEffect(() => {
    void load();
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, []);

  const running = report?.state === "running";
  const findings = report?.findings ?? [];
  const issues = findings.filter((f) => f.verdict === "issue");

  return (
    <div className="validate-panel">
      <div className="validate-bar">
        <button type="button" disabled={starting || running}
          onClick={async () => {
            setStarting(true);
            try { await runValidate(); await load(); }
            finally { setStarting(false); }
          }}>
          {running ? "Reviewing…" : "Validate narrative vs final cut"}
        </button>
        {running &&
          <span className="validate-progress">
            {report?.done ?? 0}/{report?.total ?? "?"} segments
          </span>}
      </div>
      {report?.state === "error" &&
        <p className="validate-error">⚠ {report.error}</p>}
      {report && report.state !== "error" &&
        <p className="validate-summary">
          {findings.length === 0
            ? "no findings yet"
            : `${issues.length} issue${issues.length === 1 ? "" : "s"} of ${findings.length} segments reviewed`}
        </p>}
      <ul className="validate-findings">
        {findings.map((f) => (
          <li key={f.segment} className={`finding ${f.verdict}`}>
            <b>{f.segment}</b>
            {f.beat && <span className="beat-id">{f.beat}</span>}
            <span className="finding-note">{f.note}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

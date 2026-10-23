import { useCallback, useEffect, useState } from "react";
import { fetchNarrative, saveNarrative, type NarrativeDoc, type NarrativeView } from "../api";
import type { ProjectView } from "../types";
import { Narrative, type Section } from "./Narrative";
import { CharactersSection, LocationsSection, ScenesSection } from "./Entities";

interface Props {
  project: ProjectView;
  /** bumps every time the app refreshes — the agent may have edited the
   * narrative through chat, so the view follows unless a draft is open */
  refreshTick: number;
  /** bump the app refresh after a pen save — the read model changed */
  onChanged: () => void;
}

/**
 * The stage's Storyboard view: the four digested surfaces of the
 * production — the narrative (storyboard.yaml, the base of everything)
 * and this project's characters / locations / scenes YAML blocks. Every
 * slug reference renders as a link into its section.
 */
export function Storyboard({ project, refreshTick, onChanged }: Props) {
  const [section, setSection] = useState<Section>("narrative");
  const [focus, setFocus] = useState<string | null>(null);
  const [narrative, setNarrative] = useState<NarrativeView | null>(null);
  const [doc, setDoc] = useState<NarrativeDoc | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editBeat, setEditBeat] = useState<string | null>(null);
  const dirty = doc !== null && narrative !== null && doc !== narrative.doc;

  const load = useCallback(async () => {
    const v = await fetchNarrative();
    setNarrative(v);
    setDoc(v.doc);
  }, []);

  useEffect(() => {
    if (dirty) return; // a draft is open — don't clobber it under the pen
    const controller = new AbortController();
    load().catch((e) => {
      if (!controller.signal.aborted) setError(String(e));
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  // a chip navigation scrolls to and flashes its target card
  useEffect(() => {
    if (!focus) return;
    document.getElementById(`${section}-${focus}`)
      ?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [section, focus]);

  const navigate = useCallback((s: Section, slug: string) => {
    setSection(s);
    setFocus(slug);
  }, []);

  const save = async (d: NarrativeDoc) => {
    setSaving(true);
    try {
      await saveNarrative(d);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const tab = (s: Section, label: string) => (
    <button type="button" className={section === s ? "tab on" : "tab"}
      onClick={() => setSection(s)}>{label}</button>
  );

  return (
    <div className="storyboard">
      <div className="storyboard-tabs">
        {tab("narrative", "Narrative")}
        {tab("characters", "Characters")}
        {tab("locations", "Locations")}
        {tab("scenes", "Scenes")}
      </div>
      {error && <div className="app-error" onClick={() => setError(null)}>
        {error} (click to dismiss)</div>}
      {doc && section === "narrative" &&
        <Narrative doc={doc} dirty={dirty} saving={saving}
          onChange={setDoc} onSave={save} onNavigate={navigate}
          openShot={editBeat} onOpenHandled={() => setEditBeat(null)} />}
      {section === "characters" &&
        <CharactersSection project={project} focus={focus} onChanged={onChanged} />}
      {section === "locations" &&
        <LocationsSection project={project} focus={focus} onChanged={onChanged} />}
      {section === "scenes" &&
        <ScenesSection project={project} focus={focus}
          onChanged={onChanged}
          onEditBeat={(beat) => {
            setEditBeat(beat);
            setSection("narrative");
            setFocus(beat);
          }} />}
    </div>
  );
}

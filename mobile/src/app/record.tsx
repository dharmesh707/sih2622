import { router } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Text, View } from "react-native";

import { confirm } from "../components/confirm";
import { Body, Button, Card, Chip, Field, Notice, Screen, styles } from "../components/ui";
import { EMPTY_SHORTCUTS, composeReport, parseProgress, validateReportText, type Shortcuts } from "../report";
import { useApp } from "../state/AppContext";

const DISCIPLINES = ["Piping", "Civil", "Electrical", "Instrumentation", "Mechanical", "HSE"];
const PROGRESS: { label: string; value: Shortcuts["progress"] }[] = [
  { label: "Started", value: "started" },
  { label: "25%", value: 25 },
  { label: "50%", value: 50 },
  { label: "75%", value: 75 },
  { label: "Completed", value: "completed" },
];

export default function RecordScreen() {
  const app = useApp();
  const project = app.project;
  const [text, setText] = useState("");
  const [shortcuts, setShortcuts] = useState<Shortcuts>(EMPTY_SHORTCUTS);
  const [custom, setCustom] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Restore the unsent draft for this project.
  useEffect(() => {
    if (!project) return;
    let active = true;
    app.loadDraft(project.id).then((draft) => {
      if (!active) return;
      setText(draft.text);
      setShortcuts(draft.shortcuts);
      if (typeof draft.shortcuts.progress === "number" && !PROGRESS.some((p) => p.value === draft.shortcuts.progress)) setCustom(String(draft.shortcuts.progress));
      setLoaded(true);
    });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the project changes
  }, [project?.id]);

  useEffect(() => {
    if (loaded && project) void app.saveDraft(project.id, { text, shortcuts });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- save on every edit
  }, [text, shortcuts, loaded]);

  const parsedCustom = custom.trim() ? parseProgress(custom) : null;
  const customError = parsedCustom && "error" in parsedCustom ? parsedCustom.error : null;
  const finalText = useMemo(() => composeReport(text, shortcuts), [text, shortcuts]);

  if (!project) {
    return (
      <Screen>
        <Notice tone="bad">Choose a project before recording an update.</Notice>
        <Button label="Choose project" onPress={() => router.replace("/projects")} />
      </Screen>
    );
  }

  const set = (p: Partial<Shortcuts>) => setShortcuts((s) => ({ ...s, ...p }));

  function onCustom(value: string) {
    setCustom(value);
    const parsed = parseProgress(value);
    set({ progress: "value" in parsed ? parsed.value : null });
  }

  async function submit() {
    const problem = validateReportText(finalText) ?? customError;
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      const report = await app.submit(finalText);
      router.replace({ pathname: "/result/[id]", params: { id: report.local_id } });
    } catch {
      setError("The report could not be saved on this device. Try again.");
      setBusy(false);
    }
  }

  async function discard() {
    if (!(await confirm("Discard this draft?", "The text you typed will be deleted from this phone.", "Discard"))) return;
    await app.discardDraft(project!.id);
    setText("");
    setShortcuts(EMPTY_SHORTCUTS);
    setCustom("");
  }

  return (
    <Screen>
      <Card>
        <Body muted>Reporting to</Body>
        <Text style={[styles.title, { fontSize: 20 }]}>{project.name}</Text>
      </Card>

      <Field label="What happened on site?" value={text} onChangeText={setText} multiline placeholder="Example: Piping crew completed spool XX102 at rack 3, 100%." />

      <Text style={styles.label}>Discipline (optional)</Text>
      <View style={styles.row}>
        {DISCIPLINES.map((d) => (
          <Chip key={d} label={d} selected={shortcuts.discipline === d} onPress={() => set({ discipline: shortcuts.discipline === d ? null : d })} />
        ))}
      </View>

      <Field label="Tag / equipment (optional)" value={shortcuts.identifier} onChangeText={(identifier) => set({ identifier })} placeholder="e.g. XX102, P-301" autoCapitalize="characters" />
      <Field label="Location (optional)" value={shortcuts.location} onChangeText={(location) => set({ location })} placeholder="e.g. rack 3, Unit 2" />

      <Text style={styles.label}>Progress (optional)</Text>
      <View style={styles.row}>
        {PROGRESS.map((p) => (
            <Chip
              key={p.label}
              label={p.label}
              selected={shortcuts.progress === p.value && !custom}
              onPress={() => {
                setCustom("");
                set({ progress: shortcuts.progress === p.value ? null : p.value });
              }}
            />
          ))}
      </View>
      <Field label="Other %" value={custom} onChangeText={onCustom} keyboardType="numeric" placeholder="0–100" error={customError} />

      {finalText ? (
        <Card>
          <Text style={styles.label}>Will be sent as</Text>
          <Text aria-label="Final report text" style={styles.body}>
            {finalText}
          </Text>
        </Card>
      ) : null}

      {error ? <Notice tone="bad">{error}</Notice> : null}
      <Button label={`Submit to ${project.name}`} onPress={submit} busy={busy} disabled={!finalText} />
      <Button label="Discard draft" variant="danger" onPress={discard} disabled={!text && !finalText} />
    </Screen>
  );
}


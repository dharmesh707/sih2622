import { router } from "expo-router";
import { useState } from "react";

import { Body, Button, Field, Notice, Screen, Title } from "../components/ui";
import { useApp } from "../state/AppContext";

export default function SetupScreen() {
  const app = useApp();
  const [url, setUrl] = useState(app.baseUrl ?? "");
  const [token, setToken] = useState("");
  const [name, setName] = useState(app.workerName ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    const problem = await app.saveConnection(url, token, name);
    setBusy(false);
    if (problem) return setError(problem);
    setToken("");
    router.replace(app.project ? "/home" : "/projects");
  }

  return (
    <Screen>
      <Title>Connect to ProgressSync</Title>
      <Body muted>{"Your planner gives you the server address and access token. The token is kept in this phone's secure storage and is never shown again."}</Body>
      <Field label="Server address" value={url} onChangeText={setUrl} placeholder="https://progresssync.example.com" autoCapitalize="none" autoCorrect={false} keyboardType="url" />
      <Field
        label={app.hasToken ? "Access token (leave empty to keep the saved one)" : "Access token"}
        value={token}
        onChangeText={setToken}
        secureTextEntry
        autoCapitalize="none"
        autoCorrect={false}
        placeholder={app.hasToken ? "•••••••• saved" : "Paste the token"}
      />
      <Field label="Your name (optional, stays on this phone)" value={name} onChangeText={setName} placeholder="e.g. Ravi, piping crew" />
      {error ? <Notice tone="bad">{error}</Notice> : null}
      <Button label="Save and connect" onPress={save} busy={busy} disabled={!url.trim()} />
    </Screen>
  );
}

import Constants from "expo-constants";
import { router } from "expo-router";

import { confirm } from "../components/confirm";
import { Body, Button, Card, ConnectionBanner, Screen, Title } from "../components/ui";
import { useApp } from "../state/AppContext";

export default function SettingsScreen() {
  const app = useApp();

  async function logout() {
    const ok = await confirm(
      "Remove the access token?",
      "The token is deleted from this phone. Unsent reports stay saved and will sync after you connect again.",
      "Remove token",
    );
    if (!ok) return;
    await app.logout();
    router.replace("/setup");
  }

  return (
    <Screen>
      <ConnectionBanner />
      <Card>
        <Body muted>Server</Body>
        <Body>{app.baseUrl ?? "Not set"}</Body>
        <Body muted>Access token</Body>
        <Body>{app.hasToken ? "Saved in secure storage (hidden)" : "Not set"}</Body>
        <Body muted>Project</Body>
        <Body>{app.project?.name ?? "None selected"}</Body>
        <Body muted>Your name</Body>
        <Body>{app.workerName ?? "Not set"}</Body>
      </Card>
      <Button label="Edit connection" variant="secondary" onPress={() => router.push("/setup")} />
      <Button label="Change project" variant="secondary" onPress={() => router.push("/projects")} />
      <Button label="Log out (remove token)" variant="danger" onPress={logout} disabled={!app.hasToken} />
      <Card>
        <Title>About</Title>
        <Body>ProgressSync Field {Constants.expoConfig?.version ?? ""}</Body>
        <Body muted>
          Reports you send are matched by the ProgressSync server and go to a planner. The schedule only changes after a planner confirms. Reports made without signal are kept on
          this phone and sent automatically when the server is reachable.
        </Body>
      </Card>
    </Screen>
  );
}

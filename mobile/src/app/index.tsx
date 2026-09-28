import { Redirect } from "expo-router";

import { Splash } from "../components/Splash";
import { useApp } from "../state/AppContext";

// Startup: restore the saved session, then route. Never waits on the server.
export default function Index() {
  const { ready, baseUrl, hasToken, project } = useApp();
  if (!ready) return <Splash message="Restoring your session…" />;
  if (!baseUrl || !hasToken) return <Redirect href="/setup" />;
  if (!project) return <Redirect href="/projects" />;
  return <Redirect href="/home" />;
}

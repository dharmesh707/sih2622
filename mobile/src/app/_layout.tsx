import { useEffect, useState } from "react";

import { AppShell } from "../components/AppShell";
import { Splash } from "../components/Splash";
import { createDeviceDeps } from "../deviceDeps";
import type { AppDeps } from "../state/AppContext";

export default function RootLayout() {
  const [deps, setDeps] = useState<AppDeps | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    createDeviceDeps()
      .then(setDeps)
      .catch(() => setError("This device could not open local storage. Restart the app."));
  }, []);

  if (!deps) return <Splash message={error ?? "Opening local storage…"} />;
  return <AppShell deps={deps} />;
}

import { router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, Text } from "react-native";

import { Body, Button, Card, Notice, Screen, Title, styles } from "../components/ui";
import { useApp } from "../state/AppContext";
import type { Project } from "../types";

export default function ProjectsScreen() {
  const app = useApp();
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    await app.refreshProjects();
    setLoading(false);
  }

  useEffect(() => {
    void app.refreshProjects().then(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load once on open
  }, []);

  async function choose(project: Project) {
    await app.selectProject(project);
    router.replace("/home");
  }

  const cached = app.connection !== "online" && app.projects.length > 0;

  return (
    <Screen>
      <Title>Which project are you on?</Title>
      {cached ? (
        <Notice tone="warn">
          Offline — showing the saved project list{app.projectsCachedAt ? ` from ${new Date(app.projectsCachedAt).toLocaleString()}` : ""}.
        </Notice>
      ) : null}
      {!app.projects.length && !loading ? <Notice tone="bad">No projects loaded yet. Check the connection and try again.</Notice> : null}
      {app.projects.map((project) => {
        const selected = app.project?.id === project.id;
        return (
          <Pressable key={project.id} role="button" aria-label={`Project ${project.name}`} aria-selected={selected} onPress={() => choose(project)}>
            <Card>
              <Text style={[styles.title, { fontSize: 20 }]}>{project.name}</Text>
              <Body muted>{selected ? "Current project" : `Project #${project.id}`}</Body>
            </Card>
          </Pressable>
        );
      })}
      <Button label="Reload projects" variant="secondary" onPress={refresh} busy={loading} />
    </Screen>
  );
}

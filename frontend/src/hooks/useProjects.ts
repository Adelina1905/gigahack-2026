import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "../api";
import { toProjectSummary } from "../api/mappers";
import * as cache from "../db/cache";
import type { ErrorKey } from "../i18n/messages";
import type { ProjectSummary } from "../types/chat";

const sortProjects = (projects: ProjectSummary[]) =>
  [...projects].sort((a, b) => b.updatedAt - a.updatedAt);

// The sidebar's projects, painted from the cache and then replaced by the
// server's list. Each project's chats are taken from useChats (by projectId),
// so the chats embedded in the project responses are not kept here.
export function useProjects() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<ErrorKey | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const cached = await cache.loadProjects();
      if (!cancelled && cached.length > 0) {
        setProjects((current) => (current.length > 0 ? current : cached));
      }

      try {
        const fresh = (await api.getProjects()).map(toProjectSummary);
        if (cancelled) return;
        // Keep projects created while the fetch was in flight.
        const freshIds = new Set(fresh.map((project) => project.id));
        setProjects((current) =>
          sortProjects([
            ...fresh,
            ...current.filter((project) => !freshIds.has(project.id) && !cached.some((old) => old.id === project.id)),
          ]),
        );
      } catch (loadError) {
        console.error("Failed to load projects", loadError);
        if (!cancelled) setError("projectsLoadFailed");
      } finally {
        if (!cancelled) setIsLoaded(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // As in useChats, the cache is only written after the first load.
  useEffect(() => {
    if (isLoaded) void cache.saveProjects(projects);
  }, [projects, isLoaded]);

  const upsert = useCallback((project: ProjectSummary) => {
    setProjects((current) =>
      sortProjects([project, ...current.filter((candidate) => candidate.id !== project.id)]),
    );
  }, []);

  // A project needs its server id before chats can be filed under it, so
  // creating waits for the server instead of showing a placeholder.
  const create = useCallback(
    async (name: string): Promise<ProjectSummary | null> => {
      const trimmed = name.trim();
      if (!trimmed) return null;

      try {
        const project = toProjectSummary(await api.createProject(trimmed));
        upsert(project);
        return project;
      } catch (createError) {
        console.error("Failed to create project", createError);
        setError("projectCreateFailed");
        return null;
      }
    },
    [upsert],
  );

  const rename = useCallback(
    async (projectId: string, name: string) => {
      const trimmed = name.trim();
      const previous = projects.find((project) => project.id === projectId);
      if (!previous || !trimmed || trimmed === previous.name) return;

      setProjects((current) =>
        current.map((project) => (project.id === projectId ? { ...project, name: trimmed } : project)),
      );

      try {
        upsert(toProjectSummary(await api.updateProject(projectId, trimmed)));
      } catch (renameError) {
        console.error("Failed to rename project", renameError);
        setProjects((current) =>
          current.map((project) => (project.id === projectId ? previous : project)),
        );
        setError("projectRenameFailed");
      }
    },
    [projects, upsert],
  );

  // Resolves to false when the delete failed and the project was restored,
  // so the caller can put the project's chats back as well.
  const remove = useCallback(
    async (projectId: string): Promise<boolean> => {
      const previous = projects;
      setProjects((current) => current.filter((project) => project.id !== projectId));

      try {
        await api.deleteProject(projectId);
        return true;
      } catch (deleteError) {
        if (deleteError instanceof ApiError && deleteError.status === 404) return true;
        console.error("Failed to delete project", deleteError);
        setProjects(previous);
        setError("projectDeleteFailed");
        return false;
      }
    },
    [projects],
  );

  // Mirrors the server bumping updatedAt when a chat is created in or moved into a project.
  const touch = useCallback((projectId: string) => {
    setProjects((current) =>
      sortProjects(
        current.map((project) =>
          project.id === projectId ? { ...project, updatedAt: Date.now() } : project,
        ),
      ),
    );
  }, []);

  const dismissError = useCallback(() => setError(null), []);

  return { projects, isLoaded, error, create, rename, remove, touch, dismissError };
}

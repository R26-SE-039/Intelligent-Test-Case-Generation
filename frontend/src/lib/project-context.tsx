"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export interface ActiveProject {
  id: string;
  name: string;
  description?: string;
}

interface ProjectContextValue {
  activeProject: ActiveProject | null;
  setActiveProject: (p: ActiveProject | null) => void;
}

const ProjectContext = createContext<ProjectContextValue>({
  activeProject: null,
  setActiveProject: () => {},
});

const STORAGE_KEY = "nextgenqa_active_project";

export function ProjectProvider({ children }: { children: ReactNode }) {
  // Always start with null on the FIRST render so the SSR'd HTML and the
  // initial client render match. We hydrate from localStorage in an effect
  // immediately after mount — this trades one frame of "null" UI for zero
  // hydration mismatches, which would otherwise force React to re-render
  // every consumer of useProject() and spam console warnings.
  const [activeProject, setActiveProjectState] = useState<ActiveProject | null>(null);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setActiveProjectState(JSON.parse(stored) as ActiveProject);
    } catch {
      /* corrupt JSON — leave as null */
    }
  }, []);

  const setActiveProject = (p: ActiveProject | null) => {
    setActiveProjectState(p);
    if (typeof window === "undefined") return;
    if (p) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject() {
  return useContext(ProjectContext);
}

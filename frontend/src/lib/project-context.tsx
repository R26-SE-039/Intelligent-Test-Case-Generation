"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

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
  const [activeProject, setActiveProjectState] = useState<ActiveProject | null>(null);

  // Restore from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setActiveProjectState(JSON.parse(stored));
      }
    } catch {
      // ignore
    }
  }, []);

  const setActiveProject = (p: ActiveProject | null) => {
    setActiveProjectState(p);
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

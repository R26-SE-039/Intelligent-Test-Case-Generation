"use client";

import { createContext, useContext, useState, ReactNode } from "react";

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

function getInitialProject(): ActiveProject | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? (JSON.parse(stored) as ActiveProject) : null;
  } catch {
    return null;
  }
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [activeProject, setActiveProjectState] = useState<ActiveProject | null>(getInitialProject);

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

# Agent Explorer — Architecture Diagrams

Companion to [08-agent-explorer.md](08-agent-explorer.md). All diagrams use Mermaid — they render directly in GitHub, VS Code (with Mermaid plugin), and most modern Markdown viewers.

---

## 1. High-Level System Architecture

How the three layers talk to each other when the QA clicks **Run Agent**.

```mermaid
graph TB
    subgraph Frontend["Frontend — Next.js 16 / React 19"]
        UI["Agent Explorer Page<br/>(3-panel UI)"]
        APIc["api.ts<br/>startExploration()<br/>openAgentEventStream()"]
    end

    subgraph Backend["Backend — FastAPI on port 8000"]
        REST["POST /api/v1/agent/explore<br/>(returns run_id immediately)"]
        WS["WS /ws/agent/{run_id}<br/>(typed event stream)"]
        Broker["AgentBroker<br/>(per-run pub/sub queue)"]
        Worker["asyncio.to_thread worker<br/>(runs the agent loop)"]
    end

    subgraph Agent["Agent Loop — sync Python"]
        SoM["SoM Overlay Injector<br/>(JS in page.evaluate)"]
        Hash["State Hasher<br/>(SHA-1 of URL + elements)"]
        LLM["Claude Sonnet 4.6<br/>(vision API)"]
        Exec["Playwright Action Executor<br/>(click / fill / navigate)"]
    end

    Chromium["Headed Chromium<br/>(the visible browser)"]

    UI -->|"POST intent + URL"| APIc
    APIc -->|"HTTP"| REST
    REST -->|"spawn task"| Worker
    REST -.->|"run_id"| APIc
    APIc -->|"open WebSocket"| WS

    Worker --> SoM
    SoM --> Chromium
    Chromium -->|"screenshot + element list"| Hash
    Hash --> LLM
    LLM -->|"JSON action"| Exec
    Exec --> Chromium

    Worker -->|"publish events"| Broker
    Broker -->|"queue.get()"| WS
    WS -->|"AgentEvent JSON"| APIc
    APIc -->|"setState"| UI

    classDef front fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#1e1b4b
    classDef back fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a
    classDef agent fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d
    classDef ext fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f
    class UI,APIc front
    class REST,WS,Broker,Worker back
    class SoM,Hash,LLM,Exec agent
    class Chromium ext
```

---

## 2. One Agent Iteration — Sequence Diagram

Exactly what happens in a single step of the loop. Repeat 3–12 times until termination.

```mermaid
sequenceDiagram
    autonumber
    participant Loop as Agent Loop
    participant Page as Chromium Page
    participant SoM as SoM Overlay
    participant Claude as Claude Sonnet 4.6
    participant Broker as AgentBroker
    participant UI as React UI (via WS)

    Loop->>Page: wait_for_load_state(networkidle)
    Loop->>SoM: page.evaluate(SOM_INJECT_SCRIPT)
    SoM->>Page: inject numbered red boxes
    SoM-->>Loop: elements[] (id, selector, bbox, text)

    Loop->>Page: screenshot (PNG, 1280x800)
    Page-->>Loop: bytes

    Loop->>Loop: state_hash = SHA1(url + sorted(elements))
    Loop->>Loop: novel = hash not in seen_set

    Loop->>Broker: publish "screenshot" event
    Broker->>UI: stream screenshot + b64 + novel_state

    Loop->>Claude: messages.create(model=sonnet-4-6,<br/>image=screenshot,<br/>text=intent+history+lessons+elements)
    Claude-->>Loop: JSON { thought_planner, thought_actor,<br/>thought_observer, thought_critic, action }

    Loop->>Broker: publish 4 "thought" events (one per role)
    Broker->>UI: stream colored thought cards

    alt action.type == "click" or "fill"
        Loop->>Page: locator(elements[id].selector).click() / .fill(value)
        Page-->>Loop: success / timeout
    else action.type == "discover_scenario"
        Loop->>Broker: publish "scenario_discovered"
        Broker->>UI: add scenario card
    else action.type == "complete_goal"
        Loop->>Broker: publish "coverage"
        Broker->>UI: tick sub-goal off list
    else action.type == "stop"
        Loop->>Broker: publish "done"
        Note over Loop: terminate
    end

    Loop->>Broker: publish "action" event
    Broker->>UI: stream action result

    alt novel == false AND plateau >= 3
        Loop->>Broker: publish "done" (coverage plateau)
        Note over Loop: terminate (novelty)
    end
```

---

## 3. Event Flow — What the WebSocket Carries

Every event the UI can receive, with the panel that renders it.

```mermaid
graph LR
    subgraph Events["AgentEvent types (TypeScript discriminated union)"]
        E1["status"]
        E2["screenshot"]
        E3["thought"]
        E4["action"]
        E5["scenario_discovered"]
        E6["lesson"]
        E7["coverage"]
        E8["done"]
        E9["error"]
        E10["end"]
    end

    subgraph Panels["UI Panels"]
        P1["Left: Live View<br/>(screenshot + meta)"]
        P2["Middle: Agent Reasoning<br/>(thought + action cards)"]
        P3["Right: Coverage Card"]
        P4["Right: Discovered Scenarios"]
        P5["Right: Reflexion Memory"]
        P6["Top: Status / Error Banner"]
    end

    E1 --> P6
    E2 --> P1
    E2 --> P3
    E3 --> P2
    E4 --> P2
    E5 --> P4
    E5 --> P3
    E6 --> P5
    E7 --> P3
    E8 --> P6
    E9 --> P6
    E10 --> P6

    classDef evt fill:#f3e8ff,stroke:#7c3aed,color:#1e1b4b
    classDef pan fill:#dcfce7,stroke:#16a34a,color:#14532d
    class E1,E2,E3,E4,E5,E6,E7,E8,E9,E10 evt
    class P1,P2,P3,P4,P5,P6 pan
```

---

## 4. Coverage-Driven Termination

The novel termination condition (layer 5 of the novelty stack).

```mermaid
flowchart TD
    Start([Step begins])
    Snap["Take screenshot + element list"]
    Hash["Compute state_hash"]
    NovelCheck{"hash in<br/>seen_set?"}
    Add["Add to seen_set<br/>plateau := 0"]
    Plateau["plateau := plateau + 1"]
    PlateauCheck{"plateau >=<br/>PLATEAU_LIMIT (3)?"}
    MaxCheck{"step >=<br/>max_steps?"}
    Act["Call LLM → execute action"]
    StopCheck{"action.type<br/>== 'stop'?"}
    DoneCov(["Terminate:<br/>coverage plateau"])
    DoneMax(["Terminate:<br/>max steps reached"])
    DoneStop(["Terminate:<br/>agent decided"])
    Next([Next step])

    Start --> Snap --> Hash --> NovelCheck
    NovelCheck -- novel --> Add --> Act
    NovelCheck -- known --> Plateau --> PlateauCheck
    PlateauCheck -- yes --> DoneCov
    PlateauCheck -- no --> Act
    Act --> StopCheck
    StopCheck -- yes --> DoneStop
    StopCheck -- no --> MaxCheck
    MaxCheck -- yes --> DoneMax
    MaxCheck -- no --> Next
    Next --> Snap

    classDef ok fill:#dcfce7,stroke:#16a34a,color:#14532d
    classDef warn fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef done fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
    class Add ok
    class Plateau warn
    class DoneCov,DoneMax,DoneStop done
```

---

## 5. The Five Novelty Layers — Where Each Lives in Code

Maps every novelty claim to the exact file + technique. Use this slide when the panel asks "show me where each contribution is in your codebase".

```mermaid
graph TD
    Intent["QA Intent:<br/>'check the login flow'"]

    subgraph L1["Layer 1 — Multi-role agent loop"]
        L1A["Single Claude call<br/>returns 4 role-tagged thoughts"]
        L1B["File: agent.py<br/>function: _call_vision_llm_sync"]
    end

    subgraph L2["Layer 2 — Set-of-Mark grounding"]
        L2A["Numbered red boxes drawn<br/>on every interactable element"]
        L2B["File: som_overlay.py<br/>script: SOM_INJECT_SCRIPT"]
    end

    subgraph L3["Layer 3 — DOM-diff state hashing"]
        L3A["Hash URL + sorted element fingerprints<br/>= unique state ID"]
        L3B["File: agent.py<br/>function: _state_hash"]
    end

    subgraph L4["Layer 4 — Reflexion memory"]
        L4A["Lessons from failed steps<br/>fed into next prompt"]
        L4B["File: agent.py<br/>variable: lessons[]"]
    end

    subgraph L5["Layer 5 — Coverage-driven termination"]
        L5A["Stop when no novel state<br/>for PLATEAU_LIMIT steps"]
        L5B["File: agent.py<br/>variable: plateau"]
    end

    Result["Discovered scenarios<br/>+ coverage report"]

    Intent --> L1A --> L2A --> L3A --> L4A --> L5A --> Result

    classDef layer fill:#ede9fe,stroke:#7c3aed,color:#1e1b4b
    classDef file fill:#f1f5f9,stroke:#475569,color:#0f172a,font-family:monospace
    class L1A,L2A,L3A,L4A,L5A layer
    class L1B,L2B,L3B,L4B,L5B file
```

---

## 6. File Map — Where to Point on Demo Day

If the panel asks to see the code, navigate in this order:

```mermaid
graph LR
    A["backend/app/agent_explorer/<br/>som_overlay.py"] -->|"injected JS"| B["page.evaluate"]
    C["backend/app/agent_explorer/<br/>agent.py"] -->|"orchestrates"| B
    C -->|"emits events"| D["backend/app/agent_explorer/<br/>log_broker.py"]
    E["backend/app/agent_explorer/<br/>routes.py"] -->|"spawns task"| C
    E -->|"WS subscriber"| D
    F["backend/app/main.py"] -->|"mounts"| E
    G["frontend/src/lib/api.ts"] -->|"calls"| E
    H["frontend/src/app/dashboard/<br/>agent-explorer/page.tsx"] -->|"renders"| G

    classDef back fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
    classDef front fill:#ede9fe,stroke:#7c3aed,color:#1e1b4b
    class A,C,D,E,F back
    class G,H front
```

---

## How to render these diagrams

| Environment | What to do |
|---|---|
| **GitHub** | Renders automatically on push — no plugin needed |
| **VS Code** | Install the "Markdown Preview Mermaid Support" extension, then `Ctrl+Shift+V` |
| **For PP1 slides** | Open in GitHub → right-click each diagram → "Save image as…" → drop the PNG into your slide deck |
| **Live demo** | Open this file in VS Code preview pane; flip to it when the panel asks "show me the architecture" |

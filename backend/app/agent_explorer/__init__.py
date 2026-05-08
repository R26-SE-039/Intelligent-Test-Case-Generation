"""
Agent Explorer — Agentic Goal-Driven Test Exploration.

Novelty layers:
  1. Multi-role agent loop (Plan → Act → Observe → Reflect) with role-shifting prompts
  2. Set-of-Mark (SoM) visual grounding — numbered red boxes overlaid on screenshots
  3. DOM-diff state hashing for novelty detection and coverage measurement
  4. Reflexion-style memory of failed attempts fed into next iteration
  5. Coverage-driven termination — stop when no novel state for N cycles
"""

from app.agent_explorer.agent import run_exploration, AgentEvent
from app.agent_explorer.log_broker import broker as agent_broker

__all__ = ["run_exploration", "AgentEvent", "agent_broker"]

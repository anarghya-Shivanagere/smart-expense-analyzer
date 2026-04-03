"""Explicit state machine for agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AgentState(str, Enum):
    INIT = "INIT"
    DATA_LOADED = "DATA_LOADED"
    CATEGORIZED = "CATEGORIZED"
    ANOMALIES_DETECTED = "ANOMALIES_DETECTED"
    REPORTED = "REPORTED"
    FAILED = "FAILED"


@dataclass
class StateTransition:
    previous_state: AgentState
    event: str
    next_state: AgentState


@dataclass
class StateMachine:
    state: AgentState = AgentState.INIT
    history: list[StateTransition] = field(default_factory=list)

    def transition(self, event: str, next_state: AgentState) -> StateTransition:
        transition = StateTransition(previous_state=self.state, event=event, next_state=next_state)
        self.history.append(transition)
        self.state = next_state
        return transition

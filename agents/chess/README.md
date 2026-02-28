# Chess Agents

This module adds agent-driven chess gameplay to Talk using the same pattern as Warehouse:

- deterministic state store + command engine
- ADK orchestrator agent with tool-only response discipline
- optional AI move planner

## Files

- `state_store.py`: single in-memory chess source of truth (`board`, `turn`, `mode`, `move_history`, captures).
- `commands.py`: deterministic command execution (`new_game`, `move`, `get_state`) and core-rule validation.
- `ai_agent.py`: legal-move chooser for AI turns.
- `orchestrator_agent.py`: user-facing chess orchestrator tools:
  - `run_chess_command`
  - `get_chess_state`
  - `call_chess_ai`

## State schema

`get_state()` returns:

```json
{
  "board": { "e2": "wP", "e7": "bP" },
  "turn": "white",
  "mode": "human_vs_ai",
  "human_side": "white",
  "status": "in_progress",
  "winner": null,
  "move_history": [],
  "last_move": null,
  "captured_white": [],
  "captured_black": []
}
```

## Supported commands

- Start/reset:
  - `new game`
  - `new game human vs ai as white`
  - `new game human vs human`
- Moves:
  - `e2 to e4`
  - `e2e4`
  - `move from g1 to f3`
  - `move pawn in front of king to two places`
- AI:
  - `ai move`
- State:
  - `show board state`
  - `whose turn`

Core movement rules are enforced for all pieces, including path blocking and capture legality.

## UI/UX notes

The Chess tab in `talk-ui` is a 3D board with:

- smooth move interpolation for each executed move
- cinematic capture animation with piece-specific finisher styles
- live board/state updates from `chess_state`


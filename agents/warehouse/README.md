# Warehouse Robotics Agents

ADK-powered agents for a simulated warehouse with UAV, UGV, and robotic arm. The warehouse UI (Talk → Warehouse tab) chat sends all messages to the **warehouse orchestrator agent**; the agent routes to UAV, UGV, or arm and uses tools to move, pick, drop, and avoid collisions. The deterministic command API (`/v1/warehouse/command`) remains available for programmatic use.

**Rule:** Items cannot move independently. Robots must move to the target location before they can pick or place. Each pick/place command first moves the robot to the required position, then performs the manipulation.

## Robots

| Robot | Role |
|-------|------|
| **UAV** | Maps items by flying and scanning areas |
| **UGV** | Moves items on the ground (pick from floor, drop at position) |
| **Arm** | Picks from stacks and places items on stacks |

## Chat (agent-only)

In the Warehouse tab, every message is sent to the **warehouse_orchestrator** agent. You can use natural language or short commands (e.g. "ugv pick item-1", "move towards arm", "ugv drop item-1 at 10 5"). The agent routes to the right robot and calls tools; the 3D view updates from `/v1/warehouse/state`.

## Deterministic Command API (programmatic)

The following commands are supported by `POST /v1/warehouse/command` for scripts or other clients. The Warehouse tab chat does **not** use this; it uses the agent only.

### Move

| Command | Example |
|---------|---------|
| `move <robot> [to] [the] <direction>` | `move uav north` |
| `<robot> move [to] <direction>` | `ugv move north` |
| `<robot> <direction>` | `ugv north` |
| `move the <robot> <direction>` | `move the ugv south` |
| `<robot> [move to] <x> <z>` | `ugv 10 5` (y=0 for ground) |
| `<robot> [move to] <x> <y> <z>` | `ugv 10 0 5` |

Directions: `north`, `south`, `east`, `west` (5 units per step). All positions must stay within warehouse bounds.

### UGV Pick and Drop

| Command | Example |
|---------|---------|
| `[ugv] pick <item_id>` | `pick item-1` |
| | `ugv pick item-2` |
| `[ugv] drop <item_id> [at] <x> <z>` | `drop item-1 at 10 5` |
| | `ugv drop item-2 15 20` |

- **Pick**: UGV moves to the item's position, then picks (item attaches to UGV). Items on stacks must be picked by the arm. UGV cannot pick if already carrying another item, or if the item is held by the arm.
- **Drop**: UGV moves to the drop location `(x, z)`, then drops the item there. UGV must be carrying that item. Drop position must be within warehouse bounds.

### Arm Pick from Stack and Place on Stack

| Command | Example |
|---------|---------|
| `[arm] pick from <stack_id>` | `arm pick from stack-1` |
| | `pick from stack-1` |
| `[arm] pick <stack_id>` | `pick stack-1` (shorthand) |
| `[arm] place/put <item_id> [on] <stack_id>` | `arm place item-1 on stack-2` |
| | `place item-3 stack-1` |
| | `put item-1 on stack-1` |

- **Pick from stack**: Arm moves to the stack top (top item's position), then picks. Arm cannot pick if already holding another item.
- **Place on stack**: Arm moves to the place height, then places the item on the stack. Arm must be holding that item. Stack position is derived from existing items or defaults for new stacks.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/warehouse/state` | GET | Current robots, items, warehouse bounds (for 3D view) |
| `/v1/warehouse/command` | POST | Deterministic command: move, pick, drop, pick_from_stack, place_on_stack |

### Command Request Body

```json
{
  "robot": "uav|ugv|arm",
  "action": "move|pick|drop|pick_from_stack|place_on_stack",
  "direction": "north|south|east|west",
  "item_id": "item-1",
  "stack_id": "stack-1",
  "x": 10.0,
  "y": 5.0,
  "z": 8.0
}
```

- **Move**: `robot` + `direction` (or `x`, `y`, `z` for absolute position).
- **Pick** (UGV): `robot: "ugv"`, `action: "pick"`, `item_id`.
- **Drop** (UGV): `robot: "ugv"`, `action: "drop"`, `item_id`, `x`, `z`.
- **Pick from stack** (Arm): `robot: "arm"`, `action: "pick_from_stack"`, `stack_id`.
- **Place on stack** (Arm): `robot: "arm"`, `action: "place_on_stack"`, `item_id`, `stack_id`.

## State Store

Shared in-memory state in `state_store.py`:

- **robots**: `{ id, type, position, status, current_task }`
- **items**: `{ id, position, stack_id }`
- **warehouse**: `{ width, depth, height }`

All agents and the command API read/write this store.

## Orchestrator Agent

When a chat message does **not** match a deterministic command pattern, it is sent to the `warehouse_orchestrator` agent, which routes to UAV, UGV, or arm sub-agents. Routing: call_uav (mapping), call_ugv (pick/drop/move), call_arm (stack), get_robots_state, get_warehouse_state. Sub-agents have get_robots_positions() and move_direction. All move tools enforce collision avoidance (refuse if another robot occupies the target). For natural-language queries (e.g. “what are the robots doing?”). Movement via the orchestrator depends on the LLM calling tools; for reliable UX, prefer the deterministic commands above.

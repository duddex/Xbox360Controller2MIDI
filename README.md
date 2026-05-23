# Xbox360Controller2MIDI

A Python script that reads an Xbox 360 (or compatible) gamecontroller and translates its inputs into MIDI messages in real time. A live pygame window visualizes the current state of every button, stick, trigger, and D-pad direction.

**Note**: this Python script and the README were created using Github Copilot

---

## Requirements

Python 3.10 or newer (uses the `str | None` type syntax).

Install the required packages:

```
pip install pygame mido python-rtmidi
```

---

## Running the script

```
python Xbox360Controller2MIDI.py
```

Choose a specific MIDI output port by name:

```
python Xbox360Controller2MIDI.py --port "loopMIDI Port 1"
```

List all available MIDI output port names:

```
python Xbox360Controller2MIDI.py --list-ports
```

---

## How it works

| Controller input | MIDI output |
|---|---|
| Left / right stick axes | CC (Control Change) messages |
| LT / RT triggers | CC messages |
| Buttons (A, B, X, Y, LB, RB, BACK, START, LS, RS) | NoteOn on press, NoteOff on release |
| D-pad directions | NoteOn on press, NoteOff on release |

- Axis values from the controller (`-1.0 … +1.0`) are mapped linearly to MIDI range `0 … 127`. The resting centre position maps to **64**. Triggers rest at **0** (not pressed) and reach **127** when fully pressed.
- CC messages are only sent when the quantised 7-bit value actually changes, so there is no message flooding when a stick is held still.
- All held notes are released automatically when the program exits.
- Joystick input is processed even when the visualizer window does not have focus (`SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS`).

---

## Configuration

All settings are hardcoded constants near the top of `Xbox360Controller2MIDI.py`. No config file is needed — just open the script and edit the values.

---

### MIDI output port

The port can be set in three ways, in order of priority:

**1. Command-line argument (highest priority)**

```
python Xbox360Controller2MIDI.py --port "loopMIDI Port 1"
```

Use `--list-ports` to find the exact name of your port:

```
python Xbox360Controller2MIDI.py --list-ports
```

**2. Hardcoded constant in the script**

```python
MIDI_PORT_NAME: str | None = None
```

- `None` — fall through to auto-select (see below).
- A string — always connect to that port when no `--port` argument is given.

Example:

```python
MIDI_PORT_NAME = "loopMIDI Port 1"
```

**3. Auto-select (lowest priority)**

When both the argument and the constant are `None`, the script connects to the **first** available MIDI output port.

---

### MIDI channel

```python
MIDI_CHANNEL = 0      # 0-indexed  (0 = MIDI channel 1)
```

MIDI channels are **0-indexed** in this script:

| Value | MIDI channel |
|---|---|
| `0` | Channel 1 |
| `1` | Channel 2 |
| … | … |
| `15` | Channel 16 |

All NoteOn, NoteOff, and CC messages use this single channel.

---

### Button notes and velocities

```python
BUTTON_NOTES = {
    0: (60, 100),   # A      C4
    1: (62, 100),   # B      D4
    2: (64, 100),   # X      E4
    3: (65, 100),   # Y      F4
    4: (67, 100),   # LB     G4
    5: (69, 100),   # RB     A4
    6: (71, 100),   # BACK   B4
    7: (72, 100),   # START  C5
    8: (74, 100),   # LS     D5  (stick click)
    9: (76, 100),   # RS     E5  (stick click)
}
```

Each entry maps a **button index** to a tuple `(note, velocity)`:

- `note` — MIDI note number (0–127). Middle C is 60.
- `velocity` — NoteOn velocity (1–127). NoteOff is always sent with velocity 0.

To change a button, edit its tuple. For example, to make the **A** button send note 48 (C3) at velocity 80:

```python
0: (48, 80),   # A      C3
```

**Button index reference:**

| Index | Button |
|---|---|
| 0 | A |
| 1 | B |
| 2 | X |
| 3 | Y |
| 4 | LB (left shoulder) |
| 5 | RB (right shoulder) |
| 6 | BACK |
| 7 | START |
| 8 | LS (left stick click) |
| 9 | RS (right stick click) |

---

### D-pad notes and velocities

```python
DPAD_NOTES = {
    ( 0,  1): (77, 100),   # Up    F5
    ( 0, -1): (79, 100),   # Down  G5
    (-1,  0): (81, 100),   # Left  A5
    ( 1,  0): (83, 100),   # Right B5
}
```

Each entry maps a **hat direction tuple** to `(note, velocity)`. The keys are the raw SDL hat values:

| Key | Direction |
|---|---|
| `(0, 1)` | Up |
| `(0, -1)` | Down |
| `(-1, 0)` | Left |
| `(1, 0)` | Right |

---

### Stick and trigger CC numbers

```python
AXIS_CC = {
    "left_x":  1,    # CC  1  Modulation wheel
    "left_y":  2,    # CC  2  Breath controller
    "right_x": 3,    # CC  3
    "right_y": 4,    # CC  4  Foot controller
    "lt":      11,   # CC 11  Expression
    "rt":      12,   # CC 12  Effect control 1
}
```

Each entry maps an **axis name** to a MIDI CC number (0–127). To route the left stick X-axis to CC 74 (Filter Cutoff) instead:

```python
"left_x": 74,
```

**Axis name reference:**

| Name | Controller input |
|---|---|
| `left_x` | Left stick — horizontal |
| `left_y` | Left stick — vertical |
| `right_x` | Right stick — horizontal |
| `right_y` | Right stick — vertical |
| `lt` | Left trigger |
| `rt` | Right trigger |

> **Note on axis mapping:** On most Windows/XInput drivers the axis indices above match the defaults in `AXIS_MAP`. If your controller reports axes in a different order (visible in the on-screen axes table), adjust `AXIS_MAP` at the top of `Xbox360Controller2MIDI.py` accordingly.

---

## On-screen display

The visualizer window shows:

- **Controller body** with all buttons, sticks, triggers, and D-pad highlighted when active.
- **MIDI note number** shown below each button and below each stick (for the stick-click note).
- **D-pad note numbers** shown below the D-PAD label (`U:xx D:xx L:xx R:xx`).
- **Status bar** (top): connected controller name on the left, active MIDI port on the right.
- **Axes table** (bottom left): raw axis float values.
- **CC Sent table** (bottom right): live quantised CC values currently being sent (`LX, LY, RX, RY` then `LT, RT`).
- **Pressed** bar (bottom): names of all currently held buttons.

The window is resizable and all elements scale proportionally.

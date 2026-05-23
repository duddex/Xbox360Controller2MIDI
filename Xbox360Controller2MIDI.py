"""
Xbox360Controller2MIDI.py
Xbox 360 controller → MIDI bridge with live pygame visualizer.

Requirements:
    pip install pygame mido python-rtmidi

Usage:
    python Xbox360Controller2MIDI.py              # auto-selects first MIDI output
    python Xbox360Controller2MIDI.py --list-ports # print available MIDI output ports

MIDI mapping (hardcoded – edit the constants below):
  Joystick axes  →  CC messages    (axis float -1…+1  mapped to  0…127)
  Buttons        →  NoteOn / NoteOff
  D-pad          →  NoteOn / NoteOff
"""

import os
import sys

try:
    import mido
except ImportError:
    print("ERROR: 'mido' is not installed.  Run:  pip install mido python-rtmidi")
    sys.exit(1)

try:
    import pygame
except ImportError:
    print("ERROR: 'pygame' is not installed.  Run:  pip install pygame")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Window / display
# ---------------------------------------------------------------------------
WIDTH, HEIGHT = 1100, 700
BASE_WIDTH, BASE_HEIGHT = 1100, 700
FPS = 60

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
BG     = (18,  22,  28)
PANEL  = (28,  35,  45)
TEXT   = (230, 235, 245)
MUTED  = (150, 160, 175)
ACCENT = (90,  190, 255)
PRESS  = (255, 170, 80)

# ---------------------------------------------------------------------------
# Controller constants
# ---------------------------------------------------------------------------
BUTTON_LABELS = {
    0: "A", 1: "B", 2: "X", 3: "Y",
    4: "LB", 5: "RB", 6: "BACK", 7: "START",
    8: "LS", 9: "RS",
}

AXIS_MAP = {
    "left_x": 0, "left_y": 1,
    "right_x": 2, "right_y": 3,
    "lt": 4, "rt": 5,
}

# ---------------------------------------------------------------------------
# MIDI constants  (hardcoded — edit to taste)
# ---------------------------------------------------------------------------
MIDI_CHANNEL  = 0      # 0-indexed  (0 = MIDI channel 1)

# Set to None to auto-select the first available output port,
# or a string name to target a specific port.
MIDI_PORT_NAME: str | None = None

# Button index  →  (MIDI note, velocity)
BUTTON_NOTES = {
    0: (60, 100),   # A      C4
    1: (62, 100),   # B      D4
    2: (64, 100),   # X      E4
    3: (65, 100),   # Y      F4
    4: (67, 100),   # LB     G4
    5: (69, 100),   # RB     A4
    6: (71, 100),   # BACK   B4
    7: (72, 100),   # START  C5
    8: (74, 100),   # LS     D5
    9: (76, 100),   # RS     E5
}

# D-pad hat direction  →  (MIDI note, velocity)
DPAD_NOTES = {
    ( 0,  1): (77, 100),   # Up    F5
    ( 0, -1): (79, 100),   # Down  G5
    (-1,  0): (81, 100),   # Left  A5
    ( 1,  0): (83, 100),   # Right B5
}

# Axis name  →  MIDI CC number
# Values -1.0…+1.0 are mapped to 0…127.
# Centre (0.0) maps to 64.  Triggers go 0 (released) → 127 (full press).
AXIS_CC = {
    "left_x":  1,    # CC  1  Modulation wheel
    "left_y":  2,    # CC  2  Breath controller
    "right_x": 3,    # CC  3
    "right_y": 4,    # CC  4  Foot controller
    "lt":      11,   # CC 11  Expression
    "rt":      12,   # CC 12  Effect control 1
}


# ---------------------------------------------------------------------------
# Controller state
# ---------------------------------------------------------------------------
class ControllerState:
    def __init__(self):
        self.axes    = [0.0] * 8
        self.buttons = [0]   * 10
        self.hat     = (0, 0)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class GameController2Midi:

    def __init__(self, port_name: str | None = None):
        # Allow joystick input even when this window does not have focus.
        os.environ['SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS'] = '1'
        pygame.init()
        pygame.joystick.init()

        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("Xbox 360 → MIDI  |  Controller Visualizer")
        self.clock = pygame.time.Clock()

        self.font       = pygame.font.SysFont("consolas", 22)
        self.font_small = pygame.font.SysFont("consolas", 18)

        self.state          = ControllerState()
        self.current_width  = WIDTH
        self.current_height = HEIGHT

        # MIDI transition tracking
        self.prev_buttons = [0] * 10
        self.prev_hat     = (0, 0)
        self.prev_cc      = {}   # axis_name → last sent int (0-127)

        # port_name from CLI overrides the MIDI_PORT_NAME constant
        self._requested_port = port_name
        self.midi_out        = None
        self.midi_port_name  = None

        self.joystick = None
        self._connect_first_controller()
        self._init_midi()

    # -----------------------------------------------------------------------
    # Scaling helpers
    # -----------------------------------------------------------------------
    def _sx(self, x):
        return int(x * (self.current_width  / BASE_WIDTH))

    def _sy(self, y):
        return int(y * (self.current_height / BASE_HEIGHT))

    def _sp(self, px):
        scale = min(self.current_width / BASE_WIDTH, self.current_height / BASE_HEIGHT)
        return max(1, int(px * scale))

    def _spos(self, x, y):
        return (self._sx(x), self._sy(y))

    def _srect(self, x, y, w, h):
        return pygame.Rect(self._sx(x), self._sy(y), max(4, self._sx(w)), max(4, self._sy(h)))

    # -----------------------------------------------------------------------
    # Controller
    # -----------------------------------------------------------------------
    def _connect_first_controller(self):
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
        else:
            self.joystick = None

    def _read_state(self):
        if not self.joystick:
            return
        axis_count = self.joystick.get_numaxes()
        if axis_count > len(self.state.axes):
            self.state.axes.extend([0.0] * (axis_count - len(self.state.axes)))
        for i in range(axis_count):
            self.state.axes[i] = self.joystick.get_axis(i)
        btn_count = min(self.joystick.get_numbuttons(), 10)
        for i in range(btn_count):
            self.state.buttons[i] = self.joystick.get_button(i)
        if self.joystick.get_numhats() > 0:
            self.state.hat = self.joystick.get_hat(0)
        else:
            self.state.hat = (0, 0)

    def _axis(self, name):
        idx = AXIS_MAP[name]
        return self.state.axes[idx] if idx < len(self.state.axes) else 0.0

    # -----------------------------------------------------------------------
    # MIDI
    # -----------------------------------------------------------------------
    def _init_midi(self):
        ports = mido.get_output_names()
        if not ports:
            print("[MIDI] No output ports found — MIDI disabled.")
            return
        # Priority: CLI --port  →  MIDI_PORT_NAME constant  →  first available
        name = self._requested_port or MIDI_PORT_NAME or ports[0]
        if name not in ports:
            print(f"[MIDI] Port '{name}' not found — falling back to '{ports[0]}'.")
            name = ports[0]
        try:
            self.midi_out = mido.open_output(name)
            self.midi_port_name = name
            print(f"[MIDI] Opened output port: {name}")
        except Exception as exc:
            print(f"[MIDI] Cannot open '{name}': {exc}")

    def _cc_value(self, axis_name: str) -> int:
        """Map axis float (-1…+1) to MIDI 7-bit int (0…127)."""
        raw = self._axis(axis_name)
        return max(0, min(127, int((raw + 1.0) / 2.0 * 127)))

    def _send_midi(self):
        """Detect state changes and emit NoteOn/NoteOff/CC messages."""
        if not self.midi_out or not self.joystick:
            return

        # --- Axes → CC --------------------------------------------------
        for axis_name, cc_num in AXIS_CC.items():
            cc_val = self._cc_value(axis_name)
            if self.prev_cc.get(axis_name) != cc_val:
                self.midi_out.send(mido.Message(
                    "control_change",
                    channel=MIDI_CHANNEL,
                    control=cc_num,
                    value=cc_val,
                ))
                self.prev_cc[axis_name] = cc_val

        # --- Buttons → NoteOn / NoteOff ---------------------------------
        for btn_idx, (note, vel) in BUTTON_NOTES.items():
            curr = self.state.buttons[btn_idx]
            prev = self.prev_buttons[btn_idx]
            if curr and not prev:
                self.midi_out.send(mido.Message(
                    "note_on", channel=MIDI_CHANNEL,
                    note=note, velocity=vel,
                ))
            elif not curr and prev:
                self.midi_out.send(mido.Message(
                    "note_off", channel=MIDI_CHANNEL,
                    note=note, velocity=0,
                ))

        # --- D-pad → NoteOn / NoteOff -----------------------------------
        curr_hat = self.state.hat
        prev_hat = self.prev_hat
        if curr_hat != prev_hat:
            if prev_hat in DPAD_NOTES:
                prev_note, _ = DPAD_NOTES[prev_hat]
                self.midi_out.send(mido.Message(
                    "note_off", channel=MIDI_CHANNEL,
                    note=prev_note, velocity=0,
                ))
            if curr_hat in DPAD_NOTES:
                curr_note, curr_vel = DPAD_NOTES[curr_hat]
                self.midi_out.send(mido.Message(
                    "note_on", channel=MIDI_CHANNEL,
                    note=curr_note, velocity=curr_vel,
                ))

        # Update previous state
        self.prev_buttons = list(self.state.buttons)
        self.prev_hat     = self.state.hat

    def _all_notes_off(self):
        """Release every possibly-held note before shutdown."""
        if not self.midi_out:
            return
        all_notes = [note for note, _ in BUTTON_NOTES.values()] + \
                    [note for note, _ in DPAD_NOTES.values()]
        for note in all_notes:
            self.midi_out.send(mido.Message(
                "note_off", channel=MIDI_CHANNEL, note=note, velocity=0,
            ))

    # -----------------------------------------------------------------------
    # Drawing
    # -----------------------------------------------------------------------
    def _draw_text(self, text, pos, color=TEXT, small=False):
        surf = (self.font_small if small else self.font).render(text, True, color)
        self.screen.blit(surf, pos)

    def _draw_stick(self, cx, cy, value_x, value_y, label, click_pressed=False, note=None):
        outer_r = self._sp(64)
        inner_r = self._sp(11)
        ring_color = PRESS if click_pressed else MUTED
        pygame.draw.circle(self.screen, PANEL, (cx, cy), outer_r)
        pygame.draw.circle(self.screen, ring_color, (cx, cy), outer_r, 3 if click_pressed else 2)
        marker_x = int(cx + value_x * (outer_r - inner_r - 2))
        marker_y = int(cy + value_y * (outer_r - inner_r - 2))
        pygame.draw.line(self.screen, (70, 90, 115), (cx, cy), (marker_x, marker_y), 2)
        pygame.draw.circle(self.screen, ACCENT, (marker_x, marker_y), inner_r)
        deadzone    = 0.12
        active      = abs(value_x) > deadzone or abs(value_y) > deadzone
        label_color = PRESS if active else TEXT
        gap   = self._sp(12)
        lineh = self._sp(20)
        lbl = self.font_small.render(label, True, label_color)
        self.screen.blit(lbl, (cx - lbl.get_width() // 2, cy + outer_r + gap))
        val = self.font_small.render(f"x {value_x:+.2f}  y {value_y:+.2f}", True, MUTED)
        self.screen.blit(val, (cx - val.get_width() // 2, cy + outer_r + gap + lineh))
        if note is not None:
            note_surf = self.font_small.render(f"note {note}", True, MUTED)
            self.screen.blit(note_surf, (cx - note_surf.get_width() // 2, cy + outer_r + gap + lineh * 2))

    def _draw_trigger(self, bx, by, bw, bh, value, label):
        rect = self._srect(bx, by, bw, bh)
        pygame.draw.rect(self.screen, PANEL, rect, border_radius=8)
        pygame.draw.rect(self.screen, MUTED,  rect, 2, border_radius=8)
        normalized = (value + 1.0) * 0.5
        fill_h = int((rect.height - 6) * max(0.0, min(1.0, normalized)))
        if fill_h > 0:
            fill_rect = pygame.Rect(rect.x + 3, rect.bottom - 3 - fill_h,
                                    rect.width - 6, fill_h)
            pygame.draw.rect(self.screen, PRESS, fill_rect, border_radius=6)
        lbl = self.font_small.render(label, True, TEXT)
        self.screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.y + self._sp(5)))
        val = self.font_small.render(f"{normalized:.2f}", True, MUTED)
        self.screen.blit(val, (rect.centerx - val.get_width() // 2, rect.bottom + self._sp(6)))

    def _draw_button(self, cx, cy, radius, label, pressed=False, color=(130, 145, 170), note=None):
        r = self._sp(radius)
        fill   = PRESS if pressed else color
        border = (230, 180, 120) if pressed else MUTED
        pygame.draw.circle(self.screen, fill,   (cx, cy), r)
        pygame.draw.circle(self.screen, border, (cx, cy), r, 2)
        txt = self.font_small.render(label, True, BG if pressed else TEXT)
        self.screen.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
        if note is not None:
            note_surf = self.font_small.render(str(note), True, MUTED)
            self.screen.blit(note_surf, (cx - note_surf.get_width() // 2, cy + r + self._sp(4)))

    def _draw_dpad(self, cx, cy, hat, dir_notes=None):
        arm = self._sp(26)
        gap = self._sp(5)
        segments = [
            (pygame.Rect(cx - arm // 2, cy - arm - gap, arm, arm), hat[1] > 0, "U"),
            (pygame.Rect(cx - arm // 2, cy + gap,       arm, arm), hat[1] < 0, "D"),
            (pygame.Rect(cx - arm - gap, cy - arm // 2, arm, arm), hat[0] < 0, "L"),
            (pygame.Rect(cx + gap,       cy - arm // 2, arm, arm), hat[0] > 0, "R"),
        ]
        for rect, active, lbl in segments:
            pygame.draw.rect(self.screen, PRESS if active else (90, 105, 130), rect, border_radius=5)
            pygame.draw.rect(self.screen, MUTED, rect, 2, border_radius=5)
            self._draw_text(lbl, (rect.centerx - self._sp(5), rect.centery - self._sp(9)),
                            BG if active else TEXT, small=True)
        lbl = self.font_small.render("D-PAD", True, MUTED)
        self.screen.blit(lbl, (cx - lbl.get_width() // 2, cy + arm + gap + self._sp(6)))
        if dir_notes:
            note_line = (f"U:{dir_notes.get(( 0, 1),'-')} "
                         f"D:{dir_notes.get(( 0,-1),'-')} "
                         f"L:{dir_notes.get((-1, 0),'-')} "
                         f"R:{dir_notes.get(( 1, 0),'-')}")
            note_surf = self.font_small.render(note_line, True, MUTED)
            self.screen.blit(note_surf, (cx - note_surf.get_width() // 2, cy + arm + gap + self._sp(28)))

    def _draw_status(self):
        bar_h = self._sy(52)
        pygame.draw.rect(self.screen, PANEL, pygame.Rect(0, 0, self.current_width, bar_h))

        # Controller status — left side
        if self.joystick:
            ctrl_msg   = f"Controller: {self.joystick.get_name()}"
            ctrl_color = (120, 230, 140)
        else:
            ctrl_msg   = "No controller detected."
            ctrl_color = (255, 130, 110)
        self._draw_text(ctrl_msg, (self._sx(20), self._sy(15)), ctrl_color)

        # MIDI status — right side
        if self.midi_out:
            midi_msg   = f"MIDI → {self.midi_port_name}"
            midi_color = (130, 190, 255)
        else:
            midi_msg   = "MIDI: no port"
            midi_color = (200, 80, 80)
        midi_surf = self.font_small.render(midi_msg, True, midi_color)
        self.screen.blit(midi_surf, (
            self.current_width - midi_surf.get_width() - self._sx(20),
            self._sy(17),
        ))

    def _draw_info_tables(self):
        """Four-column table below the body: axes, CC sent, note mapping."""
        y0  = self._sy(560)
        lh  = self._sp(22)

        # Column 1 — Axis values
        col1_x = self._sx(40)
        col1 = [
            ("Axes",                                        TEXT),
            (f"Left  X : {self._axis('left_x'):+.3f}",     MUTED),
            (f"Left  Y : {self._axis('left_y'):+.3f}",     MUTED),
            (f"LT      : {self._axis('lt'):+.3f}",         MUTED),
            (f"Hat     : {self.state.hat}",                 MUTED),
        ]
        # Column 2 — More axis values
        col2_x = self._sx(310)
        col2 = [
            ("",                                            TEXT),
            (f"Right X : {self._axis('right_x'):+.3f}",    MUTED),
            (f"Right Y : {self._axis('right_y'):+.3f}",    MUTED),
            (f"RT      : {self._axis('rt'):+.3f}",         MUTED),
            ("",                                            MUTED),
        ]
        # Column 3 — Live CC values being sent
        col3_x = self._sx(580)
        col3 = [
            ("CC Sent",                                                                   TEXT),
            (f"LX  CC{AXIS_CC['left_x']:>2} = {self.prev_cc.get('left_x',  0):>3}",     MUTED),
            (f"LY  CC{AXIS_CC['left_y']:>2} = {self.prev_cc.get('left_y',  0):>3}",     MUTED),
            (f"RX  CC{AXIS_CC['right_x']:>2} = {self.prev_cc.get('right_x',0):>3}",     MUTED),
            (f"RY  CC{AXIS_CC['right_y']:>2} = {self.prev_cc.get('right_y',0):>3}",     MUTED),
        ]
        # Column 4 — Continued CC
        col4_x = self._sx(800)
        col4 = [
            ("",                                                                          TEXT),
            (f"LT  CC{AXIS_CC['lt']:>2}     = {self.prev_cc.get('lt',      0):>3}",     MUTED),
            (f"RT  CC{AXIS_CC['rt']:>2}     = {self.prev_cc.get('rt',      0):>3}",     MUTED),
        ]

        for col_x, col in ((col1_x, col1), (col2_x, col2), (col3_x, col3), (col4_x, col4)):
            for i, (text, color) in enumerate(col):
                if text:
                    self._draw_text(text, (col_x, y0 + i * lh), color, small=True)

    def draw(self):
        self.current_width, self.current_height = self.screen.get_size()
        self.screen.fill(BG)
        self._draw_status()

        # --- Body silhouette ---
        body = self._srect(90, 56, 920, 496)
        pygame.draw.rect(self.screen, (35, 44, 56), body, border_radius=140)
        pygame.draw.rect(self.screen, (55, 68, 85), body, 2,  border_radius=140)

        # --- Triggers ---
        self._draw_trigger(108, 72, 44, 136, self._axis("lt"), "LT")
        self._draw_trigger(948, 72, 44, 136, self._axis("rt"), "RT")

        # --- Shoulders ---
        self._draw_button(*self._spos(210, 76), 22, "LB", bool(self.state.buttons[4]), note=BUTTON_NOTES[4][0])
        self._draw_button(*self._spos(890, 76), 22, "RB", bool(self.state.buttons[5]), note=BUTTON_NOTES[5][0])

        # --- Left stick ---
        ls = self._spos(308, 242)
        self._draw_stick(ls[0], ls[1],
                         self._axis("left_x"), self._axis("left_y"),
                         "Left Stick", bool(self.state.buttons[8]),
                         note=BUTTON_NOTES[8][0])

        # --- D-pad ---
        dp = self._spos(338, 442)
        dp_dir_notes = {direction: note for direction, (note, _) in DPAD_NOTES.items()}
        self._draw_dpad(dp[0], dp[1], self.state.hat, dp_dir_notes)

        # --- BACK / START ---
        self._draw_button(*self._spos(472, 238), 30, "BACK",  bool(self.state.buttons[6]), (110, 115, 125), note=BUTTON_NOTES[6][0])
        self._draw_button(*self._spos(628, 238), 30, "START", bool(self.state.buttons[7]), (110, 115, 125), note=BUTTON_NOTES[7][0])

        # --- Right stick ---
        rs = self._spos(648, 368)
        self._draw_stick(rs[0], rs[1],
                         self._axis("right_x"), self._axis("right_y"),
                         "Right Stick", bool(self.state.buttons[9]),
                         note=BUTTON_NOTES[9][0])

        # --- Face buttons ---
        self._draw_button(*self._spos(867, 212), 26, "Y", bool(self.state.buttons[3]), (255, 219, 79),  note=BUTTON_NOTES[3][0])
        self._draw_button(*self._spos(934, 278), 26, "B", bool(self.state.buttons[1]), (240, 92,  80),  note=BUTTON_NOTES[1][0])
        self._draw_button(*self._spos(867, 344), 26, "A", bool(self.state.buttons[0]), (94,  205, 98),  note=BUTTON_NOTES[0][0])
        self._draw_button(*self._spos(800, 278), 26, "X", bool(self.state.buttons[2]), (85,  155, 240), note=BUTTON_NOTES[2][0])

        # --- Info tables + pressed-button bar ---
        self._draw_info_tables()
        pressed = [BUTTON_LABELS[i] for i, v in enumerate(self.state.buttons)
                   if v and i in BUTTON_LABELS]
        pressed_text = "Pressed: " + (", ".join(pressed) if pressed else "None")
        self._draw_text(pressed_text, (self._sx(40), self._sy(682)), TEXT, small=True)

        pygame.display.flip()

    # -----------------------------------------------------------------------
    # Run loop
    # -----------------------------------------------------------------------
    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type in (pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED):
                    self._connect_first_controller()
            self._read_state()
            self._send_midi()
            self.draw()

        self._all_notes_off()
        if self.joystick:
            self.joystick.quit()
        if self.midi_out:
            self.midi_out.close()
        pygame.quit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Xbox 360 controller → MIDI bridge with live visualizer."
    )
    parser.add_argument(
        "--list-ports", action="store_true",
        help="Print available MIDI output port names and exit.",
    )
    parser.add_argument(
        "--port", metavar="NAME", default=None,
        help="MIDI output port name to use (overrides the MIDI_PORT_NAME constant).",
    )
    args = parser.parse_args()

    if args.list_ports:
        ports = mido.get_output_names()
        if ports:
            print("Available MIDI output ports:")
            for p in ports:
                print(f"  {p}")
        else:
            print("No MIDI output ports found.")
        return

    app = GameController2Midi(port_name=args.port)
    app.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pygame.quit()
        sys.exit(0)

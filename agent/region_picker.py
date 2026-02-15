from __future__ import annotations

import argparse
from pathlib import Path
import tkinter as tk
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int

    def clamp(self, screen_w: int, screen_h: int) -> "Rect":
        w = max(40, self.width)
        h = max(40, self.height)
        l = max(0, min(self.left, screen_w - w))
        t = max(0, min(self.top, screen_h - h))
        return Rect(l, t, w, h)

    def to_env(self) -> str:
        return f"{self.left},{self.top},{self.width},{self.height}"


class RegionPicker(tk.Tk):
    def __init__(self, title: str, color: str) -> None:
        super().__init__()

        self.title(title)
        self.attributes("-topmost", True)
        self.configure(bg="black")

        # Fullscreen transparent overlay.
        self.overrideredirect(True)
        self.attributes("-fullscreen", True)
        # Windows: treat "black" as transparent.
        try:
            self.wm_attributes("-transparentcolor", "black")
        except Exception:
            pass

        self.screen_w = self.winfo_screenwidth()
        self.screen_h = self.winfo_screenheight()

        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # initial rectangle (center-ish)
        rw, rh = 560, 240
        self.rect = Rect(
            (self.screen_w - rw) // 2,
            (self.screen_h - rh) // 2,
            rw,
            rh,
        )

        self.color = color
        self.handle_size = 10

        self._drag_mode: Optional[str] = None
        self._drag_corner: Optional[str] = None
        self._start_mouse: Tuple[int, int] = (0, 0)
        self._start_rect: Rect = self.rect

        self.result: Optional[Rect] = None

        self._draw()

        self.canvas.bind("<ButtonPress-1>", self._on_down)
        self.canvas.bind("<B1-Motion>", self._on_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_up)
        self.bind("<Escape>", lambda _e: self._cancel())

        # Force the overlay to appear and receive focus.
        # On Windows, topmost can be flaky when another app just grabbed focus.
        try:
            self.update_idletasks()
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _toolbar_bbox(self) -> Tuple[int, int, int, int]:
        # toolbar anchored near top-left of rect
        x = self.rect.left
        y = max(0, self.rect.top - 42)
        return (x, y, x + 220, y + 36)

    def _draw(self) -> None:
        self.canvas.delete("all")
        r = self.rect.clamp(self.screen_w, self.screen_h)
        self.rect = r

        l, t, w, h = r.left, r.top, r.width, r.height
        self.canvas.create_rectangle(
            l,
            t,
            l + w,
            t + h,
            outline=self.color,
            width=4,
            tags=("rect",),
        )

        # handles (corners)
        hs = self.handle_size
        corners = {
            "nw": (l, t),
            "ne": (l + w, t),
            "sw": (l, t + h),
            "se": (l + w, t + h),
        }
        for name, (cx, cy) in corners.items():
            self.canvas.create_rectangle(
                cx - hs,
                cy - hs,
                cx + hs,
                cy + hs,
                fill=self.color,
                outline="white",
                width=1,
                tags=(f"handle:{name}", "handle"),
            )

        # toolbar
        tx1, ty1, tx2, ty2 = self._toolbar_bbox()
        self.canvas.create_rectangle(
            tx1,
            ty1,
            tx2,
            ty2,
            fill="#111827",
            outline=self.color,
            width=2,
            tags=("toolbar",),
        )
        self.canvas.create_text(
            tx1 + 10,
            ty1 + 18,
            anchor="w",
            fill="white",
            font=("Segoe UI", 10, "bold"),
            text="Drag / resize, then OK",
            tags=("toolbar",),
        )

        # buttons
        def btn(x: int, label: str, tag: str) -> None:
            bw, bh = 52, 22
            y = ty1 + 7
            self.canvas.create_rectangle(
                x,
                y,
                x + bw,
                y + bh,
                fill="#0f172a",
                outline="white",
                width=1,
                tags=("btn", tag),
            )
            self.canvas.create_text(
                x + bw // 2,
                y + bh // 2,
                fill="white",
                font=("Segoe UI", 9, "bold"),
                text=label,
                tags=("btn", tag),
            )

        btn(tx2 - 58, "OK", "btn:ok")
        btn(tx2 - 116, "Reset", "btn:reset")
        btn(tx2 - 174, "Cancel", "btn:cancel")

    def _hit_test(self, x: int, y: int) -> Tuple[Optional[str], Optional[str]]:
        # returns (mode, corner) where mode in {"move","resize","button"}
        l, t, w, h = self.rect.left, self.rect.top, self.rect.width, self.rect.height
        hs = self.handle_size + 4
        corners = {
            "nw": (l, t),
            "ne": (l + w, t),
            "sw": (l, t + h),
            "se": (l + w, t + h),
        }
        for name, (cx, cy) in corners.items():
            if abs(x - cx) <= hs and abs(y - cy) <= hs:
                return ("resize", name)

        tx1, ty1, tx2, ty2 = self._toolbar_bbox()
        if tx1 <= x <= tx2 and ty1 <= y <= ty2:
            # check button tags using canvas hit
            items = self.canvas.find_overlapping(x, y, x, y)
            for it in items:
                tags = self.canvas.gettags(it)
                for tag in tags:
                    if tag.startswith("btn:"):
                        return ("button", tag)
            return ("button", None)

        if l <= x <= l + w and t <= y <= t + h:
            return ("move", None)

        return (None, None)

    def _on_down(self, e: tk.Event) -> None:
        mode, corner = self._hit_test(int(e.x), int(e.y))
        if mode == "button":
            if corner == "btn:ok":
                self._ok()
            elif corner == "btn:reset":
                self._reset()
            elif corner == "btn:cancel":
                self._cancel()
            return

        self._drag_mode = mode
        self._drag_corner = corner
        self._start_mouse = (int(e.x), int(e.y))
        self._start_rect = self.rect

    def _on_move(self, e: tk.Event) -> None:
        if not self._drag_mode:
            return
        x, y = int(e.x), int(e.y)
        sx, sy = self._start_mouse
        dx, dy = x - sx, y - sy

        r0 = self._start_rect
        if self._drag_mode == "move":
            self.rect = Rect(r0.left + dx, r0.top + dy, r0.width, r0.height)
        elif self._drag_mode == "resize" and self._drag_corner:
            l, t, w, h = r0.left, r0.top, r0.width, r0.height
            if self._drag_corner == "se":
                self.rect = Rect(l, t, w + dx, h + dy)
            elif self._drag_corner == "sw":
                self.rect = Rect(l + dx, t, w - dx, h + dy)
            elif self._drag_corner == "ne":
                self.rect = Rect(l, t + dy, w + dx, h - dy)
            elif self._drag_corner == "nw":
                self.rect = Rect(l + dx, t + dy, w - dx, h - dy)
        self._draw()

    def _on_up(self, _e: tk.Event) -> None:
        self._drag_mode = None
        self._drag_corner = None

    def _reset(self) -> None:
        rw, rh = 560, 240
        self.rect = Rect((self.screen_w - rw) // 2, (self.screen_h - rh) // 2, rw, rh)
        self._draw()

    def _ok(self) -> None:
        self.result = self.rect.clamp(self.screen_w, self.screen_h)
        self.quit()

    def _cancel(self) -> None:
        self.result = None
        self.quit()


def pick_region(title: str, color: str) -> Optional[Rect]:
    app = RegionPicker(title=title, color=color)
    app.mainloop()
    res = app.result
    try:
        app.destroy()
    except Exception:
        pass
    return res


class RegionWindowPicker(tk.Tk):
    """
    Fallback picker that uses a normal window instead of a fullscreen transparent overlay.

    The user moves/resizes the window itself to cover the desired region, then presses OK.
    This is much more reliable on Windows where transparent fullscreen overlays can be flaky
    (focus issues, virtual desktops, GPU/driver quirks).
    """

    def __init__(self, title: str, color: str, alpha: float = 0.35) -> None:
        super().__init__()
        self.title(title)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", alpha)
        except Exception:
            pass

        self.configure(bg=color)
        self.resizable(True, True)
        self.geometry("640x260+120+120")
        # Prevent shrinking so much that the OK/Cancel bar becomes unreachable.
        self.minsize(360, 140)

        self.result: Optional[Rect] = None

        # Control bar
        bar = tk.Frame(self, bg="#111827")
        bar.pack(side="bottom", fill="x")
        lbl = tk.Label(
            bar,
            text="Move/resize this window to cover the region, then click OK. (Esc = Cancel)",
            fg="white",
            bg="#111827",
            anchor="w",
            padx=10,
            pady=6,
        )
        lbl.pack(side="left", fill="x", expand=True)
        btn_cancel = tk.Button(bar, text="Cancel", command=self._cancel)
        btn_cancel.pack(side="right", padx=6, pady=6)
        btn_ok = tk.Button(bar, text="OK", command=self._ok)
        btn_ok.pack(side="right", padx=6, pady=6)

        self.bind("<Escape>", lambda _e: self._cancel())
        # Keyboard fallback in case buttons are obscured by a tiny size or other windows.
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<KP_Enter>", lambda _e: self._ok())

        try:
            self.update_idletasks()
            self.deiconify()
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _ok(self) -> None:
        # Use the outer window rectangle. A few px of titlebar/border offset is acceptable for our use.
        self.update_idletasks()
        left = int(self.winfo_x())
        top = int(self.winfo_y())
        width = int(self.winfo_width())
        height = int(self.winfo_height())
        self.result = Rect(left, top, width, height)
        self.quit()

    def _cancel(self) -> None:
        self.result = None
        self.quit()


def pick_region_window(title: str, color: str) -> Optional[Rect]:
    app = RegionWindowPicker(title=title, color=color)
    app.mainloop()
    res = app.result
    try:
        app.destroy()
    except Exception:
        pass
    return res


def pick_input_and_output() -> Tuple[Optional[Rect], Optional[Rect]]:
    inp = pick_region("Select INPUT region", "#ef4444")  # red
    if not inp:
        return (None, None)
    out = pick_region("Select OUTPUT region", "#3b82f6")  # blue
    return (inp, out)


def _upsert_env_vars(env_path: Path, updates: Dict[str, str]) -> None:
    env_path = env_path.resolve()
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    replaced: set[str] = set()
    out: list[str] = []
    for line in lines:
        raw = line
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            out.append(raw)
            continue

        key = s.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            replaced.add(key)
        else:
            out.append(raw)

    for k, v in updates.items():
        if k not in replaced:
            out.append(f"{k}={v}")

    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _save_regions_to_env(env_path: Path, inp: Optional[Rect], out: Optional[Rect]) -> None:
    updates: Dict[str, str] = {}
    if inp:
        updates["IDE_INPUT_REGION"] = inp.to_env()
        updates["IDE_INPUT_POS"] = f"{inp.left + inp.width // 2},{inp.top + inp.height // 2}"
    if out:
        updates["IDE_OUTPUT_REGION"] = out.to_env()
        updates["IDE_OUTPUT_POS"] = f"{out.left + out.width // 2},{out.top + out.height // 2}"
    if not updates:
        return
    _upsert_env_vars(env_path, updates)


def main() -> int:
    ap = argparse.ArgumentParser(description="ServerVibe region picker (writes IDE_*_REGION/POS into agent/.env)")
    ap.add_argument("--env", default=str((Path(__file__).resolve().parent / ".env").resolve()))
    ap.add_argument(
        "--mode",
        choices=["overlay", "window"],
        default="window",
        help="Picker UI mode (default: window; overlay is fullscreen transparent).",
    )
    ap.add_argument("--input", action="store_true", help="Pick only INPUT region (red)")
    ap.add_argument("--output", action="store_true", help="Pick only OUTPUT region (blue)")
    args = ap.parse_args()

    env_path = Path(args.env)
    pick = pick_region if args.mode == "overlay" else pick_region_window

    if args.input and not args.output:
        inp = pick("Select INPUT region", "#ef4444")
        _save_regions_to_env(env_path, inp, None)
        return 0
    if args.output and not args.input:
        out = pick("Select OUTPUT region", "#3b82f6")
        _save_regions_to_env(env_path, None, out)
        return 0

    inp = pick("Select INPUT region", "#ef4444")
    if not inp:
        _save_regions_to_env(env_path, None, None)
        return 0
    out = pick("Select OUTPUT region", "#3b82f6")
    _save_regions_to_env(env_path, inp, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

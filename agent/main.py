import logging
import os
import platform
import shlex
import socket
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from subprocess import PIPE, STDOUT, Popen
from typing import Any, Dict, Optional, Sequence

from dotenv import load_dotenv
from supabase import Client, create_client


# Prefer agent/.env values over inherited environment variables.
# This avoids cases where an empty/old env var blocks the intended .env config.
_DOTENV_PATH = (Path(__file__).resolve().parent / ".env").resolve()
load_dotenv(dotenv_path=_DOTENV_PATH, override=True)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
COMMAND_TIMEOUT_SEC = int(os.getenv("COMMAND_TIMEOUT_SEC", "120"))
LOG_FLUSH_INTERVAL_SEC = float(os.getenv("LOG_FLUSH_INTERVAL_SEC", "1.5"))
LOG_MAX_CHARS = int(os.getenv("LOG_MAX_CHARS", "20000"))
AGENT_USER_ID = os.getenv("AGENT_USER_ID")
POLL_INTERVAL_SEC = float(os.getenv("POLL_INTERVAL_SEC", "1.0"))
POLL_MAX_BATCH = int(os.getenv("POLL_MAX_BATCH", "20"))

# IDE chat (GUI automation) settings.
# - IDE_WINDOW_TITLE_SUBSTR: window title substring to activate (e.g. "Visual Studio Code", "Cursor", "Antigravity")
# - IDE_INPUT_POS / IDE_OUTPUT_POS: click targets like "960,980" (x,y) for input box and transcript/log area
# - IDE_CHAT_FOCUS_HOTKEY: optional keys like "ctrl+l" to focus chat input (leave empty to skip)
# - IDE_RESPONSE_WAIT_SEC: fixed wait for MVP (default 15s)
# - AI_ANSWER_MARKERS: comma-separated markers for extracting the last assistant answer from copied transcript
IDE_TARGET = os.getenv("IDE_TARGET", "vscode").strip().lower()
IDE_WINDOW_TITLE_SUBSTR = os.getenv("IDE_WINDOW_TITLE_SUBSTR", "").strip()
IDE_INPUT_POS = os.getenv("IDE_INPUT_POS", "").strip()
IDE_OUTPUT_POS = os.getenv("IDE_OUTPUT_POS", "").strip()
IDE_OPEN_CHAT_HOTKEY = os.getenv("IDE_OPEN_CHAT_HOTKEY", "").strip().lower()
IDE_CHAT_FOCUS_HOTKEY = os.getenv("IDE_CHAT_FOCUS_HOTKEY", "").strip().lower()
IDE_FOCUS_TRANSCRIPT_HOTKEY = os.getenv("IDE_FOCUS_TRANSCRIPT_HOTKEY", "").strip().lower()
IDE_COPY_TRANSCRIPT_HOTKEY = os.getenv("IDE_COPY_TRANSCRIPT_HOTKEY", "").strip().lower()
IDE_INPUT_IMAGE = os.getenv("IDE_INPUT_IMAGE", "").strip()
IDE_OUTPUT_IMAGE = os.getenv("IDE_OUTPUT_IMAGE", "").strip()
IDE_IMAGE_TIMEOUT_SEC = float(os.getenv("IDE_IMAGE_TIMEOUT_SEC", "4.0"))
IDE_IMAGE_CONFIDENCE = float(os.getenv("IDE_IMAGE_CONFIDENCE", "0.85"))
IDE_LEARN_TEMPLATE_W = int(os.getenv("IDE_LEARN_TEMPLATE_W", "320"))
IDE_LEARN_TEMPLATE_H = int(os.getenv("IDE_LEARN_TEMPLATE_H", "160"))
IDE_LEARN_COUNTDOWN_SEC = float(os.getenv("IDE_LEARN_COUNTDOWN_SEC", "5"))
IDE_RESPONSE_WAIT_SEC = float(os.getenv("IDE_RESPONSE_WAIT_SEC", "15"))
AI_ANSWER_MARKERS = os.getenv(
    "AI_ANSWER_MARKERS",
    "Assistant:,AI:,Codex:,Claude:,Cursor:,Antigravity:,답변:,Assistant",
).strip()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("server-vibe-agent")


if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_KEY are required in .env")

logger.info(
    "IDE config: title_substr=%r open_hotkey=%r focus_hotkey=%r input_image=%r output_image=%r input_pos=%r output_pos=%r wait=%.1fs img_timeout=%.1fs img_conf=%.2f",
    IDE_WINDOW_TITLE_SUBSTR,
    IDE_OPEN_CHAT_HOTKEY,
    IDE_CHAT_FOCUS_HOTKEY,
    IDE_INPUT_IMAGE,
    IDE_OUTPUT_IMAGE,
    IDE_INPUT_POS,
    IDE_OUTPUT_POS,
    IDE_RESPONSE_WAIT_SEC,
    IDE_IMAGE_TIMEOUT_SEC,
    IDE_IMAGE_CONFIDENCE,
)

def _acquire_single_instance_guard() -> None:
    """
    Prevent accidental double-runs.

    We use a localhost TCP bind as a robust cross-platform singleton guard.
    File locks can be flaky across shells/launchers on Windows.
    """
    lock_port = int(os.getenv("AGENT_LOCK_PORT", "45321"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", lock_port))
        sock.listen(1)
    except Exception:
        raise RuntimeError(
            "Another Server Vibe agent instance is already running "
            f"(lock port {lock_port} is in use). Stop the existing one (Ctrl+C) and try again."
        )

    # Keep socket alive for the process lifetime.
    globals()["_SINGLE_INSTANCE_GUARD_SOCKET"] = sock


_acquire_single_instance_guard()


supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


APP_COMMANDS_WINDOWS = {
    "chrome": "start chrome",
    "vscode": "start code",
    "notepad": "start notepad",
    "explorer": "start explorer",
    "terminal": "start wt",
    "powershell": "start powershell",
}


def _truncate_log(log_text: str) -> str:
    if len(log_text) <= LOG_MAX_CHARS:
        return log_text
    tail = log_text[-LOG_MAX_CHARS:]
    return "[log truncated]\n" + tail


def update_command(
    command_id: str,
    status: str,
    response_log: Optional[str] = None,
    image_url: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {"status": status}
    if response_log is not None:
        payload["response_log"] = _truncate_log(response_log)
    if image_url is not None:
        payload["image_url"] = image_url

    supabase.table("commands").update(payload).eq("id", command_id).execute()


def capture_screen(user_id: str) -> Dict[str, Optional[str]]:
    import pyautogui

    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_path = f"{user_id}/{now}.png"

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / "capture.png"
        screenshot = pyautogui.screenshot()
        screenshot.save(local_path)

        with open(local_path, "rb") as f:
            supabase.storage.from_("screenshots").upload(
                object_path,
                f,
                {"content-type": "image/png", "upsert": "true"},
            )

    public_url_result = supabase.storage.from_("screenshots").get_public_url(object_path)
    if isinstance(public_url_result, dict):
        image_url = public_url_result.get("publicURL") or public_url_result.get("publicUrl")
    else:
        image_url = str(public_url_result)

    return {"log": f"Screenshot uploaded: {object_path}", "image_url": image_url}


def open_app(app_name: str) -> str:
    if platform.system().lower() == "windows":
        cmd = APP_COMMANDS_WINDOWS.get(app_name.lower())
        if not cmd:
            allowed = ", ".join(sorted(APP_COMMANDS_WINDOWS.keys()))
            raise ValueError(f"Unsupported app '{app_name}'. Allowed: {allowed}")
        Popen(cmd, shell=True)
        return f"Opened app: {app_name}"

    Popen(shlex.split(app_name))
    return f"Attempted to open: {app_name}"


def run_shell_command(command_id: str, command_text: str) -> str:
    process = Popen(
        command_text,
        stdout=PIPE,
        stderr=STDOUT,
        shell=True,
        text=True,
        bufsize=1,
    )

    buffer = []
    last_flush = time.time()

    def flush_partial(force: bool = False) -> None:
        nonlocal last_flush
        if not buffer:
            return
        if not force and (time.time() - last_flush) < LOG_FLUSH_INTERVAL_SEC:
            return
        partial = "".join(buffer)
        update_command(command_id, "processing", response_log=partial)
        last_flush = time.time()

    def watchdog() -> None:
        try:
            process.wait(timeout=COMMAND_TIMEOUT_SEC)
        except Exception:
            process.kill()

    guard = threading.Thread(target=watchdog, daemon=True)
    guard.start()

    assert process.stdout is not None
    for line in process.stdout:
        buffer.append(line)
        flush_partial(force=False)

    exit_code = process.wait()
    final_log = "".join(buffer)
    if not final_log.strip():
        final_log = "(no output)"

    if exit_code != 0:
        raise RuntimeError(f"Command failed with exit code {exit_code}\n\n{final_log}")

    return final_log


def _parse_xy(spec: str) -> Optional[tuple[int, int]]:
    if not spec:
        return None
    parts = [p.strip() for p in spec.split(",")]
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None


def _hotkey_from_spec(spec: str) -> Sequence[str]:
    # Example: "ctrl+l" -> ["ctrl", "l"], "ctrl+shift+p" -> ["ctrl","shift","p"]
    keys = [k.strip() for k in spec.split("+") if k.strip()]
    return keys if keys else ["ctrl", "l"]

def _resolve_asset_path(p: str) -> str:
    """
    Resolve relative paths (from agent folder) for image templates.
    """
    if not p:
        return ""
    pp = Path(p)
    if pp.is_absolute():
        return str(pp)
    return str((Path(__file__).resolve().parent / pp).resolve())


def _click_by_image(pyautogui_mod: Any, image_path: str, timeout_sec: float) -> bool:
    """
    Best-effort image-based click. This avoids hard-coded coordinates but requires stable UI visuals.
    """
    if not image_path:
        return False
    resolved = _resolve_asset_path(image_path)
    if not Path(resolved).exists():
        raise RuntimeError(f"Image template not found: {resolved}")

    deadline = time.time() + max(0.1, timeout_sec)
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            # confidence requires opencv; if missing, fall back to exact match.
            try:
                pos = pyautogui_mod.locateCenterOnScreen(
                    resolved, confidence=IDE_IMAGE_CONFIDENCE, grayscale=True
                )
            except Exception:
                pos = pyautogui_mod.locateCenterOnScreen(resolved, grayscale=True)

            if pos:
                pyautogui_mod.click(pos.x, pos.y)
                return True
        except Exception as e:
            last_err = e
        time.sleep(0.1)

    if last_err:
        logger.debug("Image locate failed: %s", last_err)
    return False


def _clipboard_wait_for_change(old: str, timeout_sec: float = 3.0) -> str:
    import pyperclip

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        cur = pyperclip.paste() or ""
        if cur != old and cur.strip():
            return cur
        time.sleep(0.05)
    return pyperclip.paste() or ""


def _extract_last_ai_answer(full_text: str) -> str:
    text = (full_text or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    markers = [m.strip() for m in AI_ANSWER_MARKERS.split(",") if m.strip()]
    lowered = text.lower()

    # Find the last marker occurrence (case-insensitive).
    best_idx = -1
    best_marker = ""
    for m in markers:
        idx = lowered.rfind(m.lower())
        if idx > best_idx:
            best_idx = idx
            best_marker = m

    if best_idx >= 0:
        # Return everything after the marker on that line.
        cut = text[best_idx + len(best_marker) :].lstrip()
        return cut.strip()

    # Fallback: return the last ~120 lines (keeps UI usable).
    lines = text.split("\n")
    tail = "\n".join(lines[-120:])
    return tail.strip()


def ide_chat_via_gui(question: str) -> Dict[str, Optional[str]]:
    """
    Send a natural-language question into an IDE chat UI via GUI automation,
    then copy the transcript to clipboard and extract the latest assistant reply.

    This is intentionally MVP-simple:
    - fixed sleep for response time
    - click targets are configured via .env coordinates
    """
    import pyautogui
    import pygetwindow
    import pyperclip

    if platform.system().lower() != "windows":
        raise RuntimeError("IDE GUI automation is only implemented for Windows right now.")

    if not IDE_WINDOW_TITLE_SUBSTR:
        raise RuntimeError("IDE_WINDOW_TITLE_SUBSTR is required for IDE chat automation.")

    input_xy = _parse_xy(IDE_INPUT_POS)
    output_xy = _parse_xy(IDE_OUTPUT_POS)

    wins = pygetwindow.getWindowsWithTitle(IDE_WINDOW_TITLE_SUBSTR)
    if not wins:
        raise RuntimeError(f"No window found with title containing: {IDE_WINDOW_TITLE_SUBSTR!r}")

    def _score_window(w: Any) -> int:
        score = 0
        try:
            if getattr(w, "isActive", False):
                score += 1_000_000
        except Exception:
            pass
        try:
            if not getattr(w, "isMinimized", False):
                score += 100_000
        except Exception:
            pass
        try:
            score += int(getattr(w, "width", 0)) * int(getattr(w, "height", 0))
        except Exception:
            pass
        return score

    def _choose_best_window(candidates: Sequence[Any]) -> Any:
        return max(candidates, key=_score_window)

    def _activate_window_once(best_win: Any) -> None:
        # Prefer a robust Win32 activation path; pygetwindow.activate() can be flaky.
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = getattr(best_win, "_hWnd", None)
            if not hwnd:
                raise RuntimeError("Window handle not available.")

            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)

            # Try to bring to foreground even if another thread owns focus.
            fg = user32.GetForegroundWindow()
            cur_tid = user32.GetWindowThreadProcessId(fg, None)
            tgt_tid = user32.GetWindowThreadProcessId(hwnd, None)
            if cur_tid != tgt_tid:
                user32.AttachThreadInput(cur_tid, tgt_tid, True)
                try:
                    user32.SetForegroundWindow(hwnd)
                    user32.SetFocus(hwnd)
                finally:
                    user32.AttachThreadInput(cur_tid, tgt_tid, False)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.SetFocus(hwnd)
        except Exception:
            # Fall back to pygetwindow if ctypes activation fails.
            best_win.restore()
            time.sleep(0.1)
            best_win.activate()

    def _activate_window_with_retries(best_win: Any, attempts: int = 6) -> None:
        last_exc: Optional[Exception] = None
        for _ in range(max(1, attempts)):
            try:
                _activate_window_once(best_win)
                return
            except Exception as e:
                last_exc = e
                time.sleep(0.15)
        raise RuntimeError(f"Failed to activate window after {attempts} attempt(s): {last_exc}")

    win = _choose_best_window(wins)
    _activate_window_with_retries(win, attempts=6)

    time.sleep(0.15)

    # Optional: open chat panel first (depends on your VS Code/Codex keybinding).
    if IDE_OPEN_CHAT_HOTKEY:
        pyautogui.hotkey(*_hotkey_from_spec(IDE_OPEN_CHAT_HOTKEY))
        time.sleep(0.1)

    # Always paste (pyautogui typewrite can't handle Korean reliably).
    pyperclip.copy(question)

    # Focus input box: prefer hotkey -> image -> coordinates.
    if IDE_CHAT_FOCUS_HOTKEY:
        pyautogui.hotkey(*_hotkey_from_spec(IDE_CHAT_FOCUS_HOTKEY))
        time.sleep(0.05)
    else:
        clicked = _click_by_image(pyautogui, IDE_INPUT_IMAGE, IDE_IMAGE_TIMEOUT_SEC)
        if clicked:
            time.sleep(0.05)
        elif input_xy:
            pyautogui.click(input_xy[0], input_xy[1])
            time.sleep(0.05)
        else:
            raise RuntimeError(
                "No way to focus input. Set IDE_CHAT_FOCUS_HOTKEY or IDE_INPUT_IMAGE or IDE_INPUT_POS."
            )

    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.05)
    pyautogui.press("enter")

    time.sleep(max(0.0, IDE_RESPONSE_WAIT_SEC))

    # Copy transcript/log area.
    sentinel = f"__server_vibe_clip_sentinel_{time.time_ns()}__"
    pyperclip.copy(sentinel)

    # Focus transcript: hotkey -> image -> coordinates.
    if IDE_FOCUS_TRANSCRIPT_HOTKEY:
        pyautogui.hotkey(*_hotkey_from_spec(IDE_FOCUS_TRANSCRIPT_HOTKEY))
        time.sleep(0.05)
    else:
        clicked = _click_by_image(pyautogui, IDE_OUTPUT_IMAGE, IDE_IMAGE_TIMEOUT_SEC)
        if clicked:
            time.sleep(0.05)
        elif output_xy:
            pyautogui.click(output_xy[0], output_xy[1])
            time.sleep(0.05)
        else:
            raise RuntimeError(
                "No way to focus transcript. Set IDE_FOCUS_TRANSCRIPT_HOTKEY or IDE_OUTPUT_IMAGE or IDE_OUTPUT_POS."
            )

    if IDE_COPY_TRANSCRIPT_HOTKEY:
        pyautogui.hotkey(*_hotkey_from_spec(IDE_COPY_TRANSCRIPT_HOTKEY))
    else:
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "c")
    copied = _clipboard_wait_for_change(sentinel, timeout_sec=3.0)

    answer = _extract_last_ai_answer(copied)
    if not answer:
        answer = "(no answer extracted)"

    return {"log": answer, "image_url": None}


def ide_status() -> str:
    """
    Return a concise snapshot of the current IDE-bridge configuration and readiness.

    This is designed to answer: "Why is IDE chat failing?"
    """
    input_xy = _parse_xy(IDE_INPUT_POS)
    output_xy = _parse_xy(IDE_OUTPUT_POS)

    input_img = _resolve_asset_path(IDE_INPUT_IMAGE) if IDE_INPUT_IMAGE else ""
    output_img = _resolve_asset_path(IDE_OUTPUT_IMAGE) if IDE_OUTPUT_IMAGE else ""

    lines: list[str] = []
    lines.append(f"dotenv_path: {_DOTENV_PATH}")
    lines.append(f"IDE_WINDOW_TITLE_SUBSTR: {IDE_WINDOW_TITLE_SUBSTR!r}")
    lines.append(f"IDE_OPEN_CHAT_HOTKEY: {IDE_OPEN_CHAT_HOTKEY!r}")
    lines.append(f"IDE_CHAT_FOCUS_HOTKEY: {IDE_CHAT_FOCUS_HOTKEY!r}")
    lines.append(f"IDE_FOCUS_TRANSCRIPT_HOTKEY: {IDE_FOCUS_TRANSCRIPT_HOTKEY!r}")
    lines.append(f"IDE_COPY_TRANSCRIPT_HOTKEY: {IDE_COPY_TRANSCRIPT_HOTKEY!r}")
    lines.append(f"IDE_INPUT_POS: {IDE_INPUT_POS!r} -> {input_xy}")
    lines.append(f"IDE_OUTPUT_POS: {IDE_OUTPUT_POS!r} -> {output_xy}")
    lines.append(
        f"IDE_INPUT_IMAGE: {IDE_INPUT_IMAGE!r} -> {input_img} (exists={bool(input_img and Path(input_img).exists())})"
    )
    lines.append(
        f"IDE_OUTPUT_IMAGE: {IDE_OUTPUT_IMAGE!r} -> {output_img} (exists={bool(output_img and Path(output_img).exists())})"
    )
    lines.append(f"IDE_IMAGE_TIMEOUT_SEC: {IDE_IMAGE_TIMEOUT_SEC}")
    lines.append(f"IDE_IMAGE_CONFIDENCE: {IDE_IMAGE_CONFIDENCE}")
    lines.append(f"IDE_LEARN_COUNTDOWN_SEC: {IDE_LEARN_COUNTDOWN_SEC}")
    lines.append(f"IDE_RESPONSE_WAIT_SEC: {IDE_RESPONSE_WAIT_SEC}")

    try:
        import cv2  # type: ignore

        _ = cv2.__version__
        lines.append("opencv_available: True")
    except Exception:
        lines.append("opencv_available: False")

    focus_ok = bool(IDE_CHAT_FOCUS_HOTKEY or IDE_INPUT_IMAGE or input_xy)
    transcript_ok = bool(IDE_FOCUS_TRANSCRIPT_HOTKEY or IDE_OUTPUT_IMAGE or output_xy)
    lines.append(f"focus_input_configured: {focus_ok}")
    lines.append(f"focus_transcript_configured: {transcript_ok}")

    try:
        import pygetwindow

        if IDE_WINDOW_TITLE_SUBSTR:
            wins = pygetwindow.getWindowsWithTitle(IDE_WINDOW_TITLE_SUBSTR)
            lines.append(f"window_matches: {len(wins)}")
            titles = []
            for w in wins[:5]:
                t = (getattr(w, "title", "") or "").strip()
                if t:
                    titles.append(t[:80])
            if titles:
                lines.append("window_titles_sample:")
                for t in titles:
                    lines.append(f"- {t}")
        else:
            lines.append("window_matches: (skipped; IDE_WINDOW_TITLE_SUBSTR is empty)")
    except Exception as e:
        lines.append(f"window_check_error: {e}")

    if not IDE_WINDOW_TITLE_SUBSTR:
        lines.append("WARN: IDE_WINDOW_TITLE_SUBSTR is empty (IDE chat will fail).")
    if not focus_ok:
        lines.append("WARN: No input focus method configured (set IDE_CHAT_FOCUS_HOTKEY or IDE_INPUT_IMAGE or IDE_INPUT_POS).")
    if not transcript_ok:
        lines.append("WARN: No transcript focus method configured (set IDE_FOCUS_TRANSCRIPT_HOTKEY or IDE_OUTPUT_IMAGE or IDE_OUTPUT_POS).")

    return "\n".join(lines)


def _storage_public_url_from_upload(object_path: str) -> str:
    public_url_result = supabase.storage.from_("screenshots").get_public_url(object_path)
    if isinstance(public_url_result, dict):
        return public_url_result.get("publicURL") or public_url_result.get("publicUrl") or ""
    return str(public_url_result)


def ide_debug_screen(user_id: str, label: str = "ide_debug_screen") -> Dict[str, str]:
    import pyautogui

    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_path = f"{user_id}/debug/{label}_{now}.png"
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / "debug.png"
        img = pyautogui.screenshot()
        img.save(local_path)
        with open(local_path, "rb") as f:
            supabase.storage.from_("screenshots").upload(
                object_path,
                f,
                {"content-type": "image/png", "upsert": "true"},
            )
    image_url = _storage_public_url_from_upload(object_path)
    return {"log": f"Uploaded debug screen: {object_path}", "image_url": image_url}


def ide_debug_locate(user_id: str, kind: str) -> Dict[str, Optional[str]]:
    """
    Try to locate input/output template on screen, and upload an annotated screenshot.
    """
    import pyautogui
    from PIL import ImageDraw

    if kind not in ("input", "output"):
        raise ValueError("Usage: /ide debug locate input|output")

    template_env = IDE_INPUT_IMAGE if kind == "input" else IDE_OUTPUT_IMAGE
    if not template_env:
        raise RuntimeError(f"IDE_{kind.upper()}_IMAGE is empty. Set it to an image template path first.")

    template_path = _resolve_asset_path(template_env)
    if not Path(template_path).exists():
        raise RuntimeError(f"Image template not found: {template_path}")

    box = None
    last_err: Optional[Exception] = None
    deadline = time.time() + max(0.1, IDE_IMAGE_TIMEOUT_SEC)
    while time.time() < deadline and box is None:
        try:
            try:
                box = pyautogui.locateOnScreen(
                    template_path, confidence=IDE_IMAGE_CONFIDENCE, grayscale=True
                )
            except Exception:
                box = pyautogui.locateOnScreen(template_path, grayscale=True)
        except Exception as e:
            last_err = e
        if box is None:
            time.sleep(0.1)

    img = pyautogui.screenshot()
    draw = ImageDraw.Draw(img)

    status = "not_found"
    details = f"template={template_path} timeout={IDE_IMAGE_TIMEOUT_SEC}s conf={IDE_IMAGE_CONFIDENCE}"
    if box is not None:
        status = "found"
        left, top, width, height = int(box.left), int(box.top), int(box.width), int(box.height)
        draw.rectangle([left, top, left + width, top + height], outline=(255, 0, 0), width=6)
        draw.rectangle([left - 2, top - 2, left + width + 2, top + height + 2], outline=(255, 255, 255), width=2)
        details = f"{details}\nbox=({left},{top},{width},{height})"
    elif last_err is not None:
        details = f"{details}\nlocate_error={last_err}"

    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_path = f"{user_id}/debug/locate_{kind}_{status}_{now}.png"
    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / "annotated.png"
        img.save(local_path)
        with open(local_path, "rb") as f:
            supabase.storage.from_("screenshots").upload(
                object_path,
                f,
                {"content-type": "image/png", "upsert": "true"},
            )
    image_url = _storage_public_url_from_upload(object_path)

    return {"log": f"/ide debug locate {kind}: {status}\n{details}", "image_url": image_url}


def _learn_template_at_mouse(user_id: str, kind: str) -> Dict[str, str]:
    """
    Save a small screenshot region around current mouse position as a template image.
    This helps avoid per-user coordinate config.
    """
    import pyautogui

    if kind not in ("input", "output"):
        raise ValueError("kind must be 'input' or 'output'")

    # Single-PC friendly: give time to move the mouse after triggering from mobile.
    if IDE_LEARN_COUNTDOWN_SEC > 0:
        time.sleep(IDE_LEARN_COUNTDOWN_SEC)

    p = pyautogui.position()
    w = max(40, IDE_LEARN_TEMPLATE_W)
    h = max(40, IDE_LEARN_TEMPLATE_H)
    left = max(0, int(p.x - w // 2))
    top = max(0, int(p.y - h // 2))

    assets_dir = Path(__file__).resolve().parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    out_path = assets_dir / f"ide_{kind}_template.png"

    img = pyautogui.screenshot(region=(left, top, w, h))
    img.save(out_path)

    # Upload so you can visually confirm the template from the web UI.
    now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    object_path = f"{user_id}/templates/ide_{kind}_template_{now}.png"
    with open(out_path, "rb") as f:
        supabase.storage.from_("screenshots").upload(
            object_path,
            f,
            {"content-type": "image/png", "upsert": "true"},
        )

    public_url_result = supabase.storage.from_("screenshots").get_public_url(object_path)
    if isinstance(public_url_result, dict):
        image_url = public_url_result.get("publicURL") or public_url_result.get("publicUrl") or ""
    else:
        image_url = str(public_url_result)

    # Also upload a full-screen debug image marking the captured region.
    debug_object_path = f"{user_id}/debug/learn_{kind}_region_{now}.png"
    try:
        from PIL import ImageDraw

        full = pyautogui.screenshot()
        draw = ImageDraw.Draw(full)
        draw.rectangle([left, top, left + w, top + h], outline=(255, 0, 0), width=8)
        draw.rectangle([left - 2, top - 2, left + w + 2, top + h + 2], outline=(255, 255, 255), width=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "learn_region.png"
            full.save(local_path)
            with open(local_path, "rb") as f:
                supabase.storage.from_("screenshots").upload(
                    debug_object_path,
                    f,
                    {"content-type": "image/png", "upsert": "true"},
                )
    except Exception as e:
        logger.debug("Failed to upload learn debug image: %s", e)

    debug_url = _storage_public_url_from_upload(debug_object_path)

    return {
        "path": str(out_path),
        "image_url": image_url,
        "debug_image_url": debug_url,
        "mouse_pos": f"{int(p.x)},{int(p.y)}",
        "region": f"{left},{top},{w},{h}",
    }


def handle_command(payload: Dict[str, Any]) -> None:
    row = payload.get("new", payload)
    command_id = row.get("id")
    user_id = row.get("user_id")
    command_text = (row.get("command_text") or "").strip()
    status = row.get("status")

    if not command_id or not user_id:
        logger.warning("Skipping malformed row: %s", row)
        return

    if AGENT_USER_ID and user_id != AGENT_USER_ID:
        return

    if status != "pending":
        return

    if not command_text:
        update_command(command_id, "error", response_log="Empty command_text")
        return

    # Claim the job atomically to avoid double-processing if the agent is run twice.
    claim = (
        supabase.table("commands")
        .update({"status": "processing", "response_log": "Command received"})
        .eq("id", command_id)
        .eq("status", "pending")
        .execute()
    )
    claimed_rows = claim.data or []
    if not claimed_rows:
        return

    logger.info("Processing command %s: %s", command_id, command_text)

    try:
        if command_text == "/pos":
            import pyautogui

            p = pyautogui.position()
            update_command(command_id, "completed", response_log=f"{p.x},{p.y}")
            return

        if command_text == "/ide learn input":
            learned = _learn_template_at_mouse(user_id, "input")
            update_command(
                command_id,
                "completed",
                response_log=(
                    f"Saved input template: {learned['path']}\n"
                    f"mouse_pos={learned.get('mouse_pos')}\n"
                    f"region={learned.get('region')}\n"
                    f"template_url={learned.get('image_url')}\n"
                    "Set IDE_INPUT_IMAGE=assets\\ide_input_template.png"
                ),
                image_url=learned.get("debug_image_url") or learned.get("image_url") or None,
            )
            return

        if command_text == "/ide learn output":
            learned = _learn_template_at_mouse(user_id, "output")
            update_command(
                command_id,
                "completed",
                response_log=(
                    f"Saved output template: {learned['path']}\n"
                    f"mouse_pos={learned.get('mouse_pos')}\n"
                    f"region={learned.get('region')}\n"
                    f"template_url={learned.get('image_url')}\n"
                    "Set IDE_OUTPUT_IMAGE=assets\\ide_output_template.png"
                ),
                image_url=learned.get("debug_image_url") or learned.get("image_url") or None,
            )
            return

        if command_text == "/ide status":
            update_command(command_id, "completed", response_log=ide_status())
            return

        if command_text == "/ide debug screen":
            result = ide_debug_screen(user_id)
            update_command(
                command_id,
                "completed",
                response_log=result["log"],
                image_url=result["image_url"],
            )
            return

        if command_text.startswith("/ide debug locate "):
            kind = command_text.replace("/ide debug locate ", "", 1).strip().lower()
            result = ide_debug_locate(user_id, kind)
            update_command(
                command_id,
                "completed",
                response_log=result["log"],
                image_url=result["image_url"],
            )
            return

        if command_text == "/capture":
            result = capture_screen(user_id)
            update_command(
                command_id,
                "completed",
                response_log=result["log"],
                image_url=result["image_url"],
            )
            return

        if command_text.startswith("/open "):
            app_name = command_text.replace("/open ", "", 1).strip()
            if not app_name:
                raise ValueError("Usage: /open [app_name]")
            out = open_app(app_name)
            update_command(command_id, "completed", response_log=out)
            return

        # Back-compat: allow the classic smoke-test command without requiring /sh.
        if command_text.strip().lower() == "whoami":
            out = run_shell_command(command_id, "whoami")
            update_command(command_id, "completed", response_log=out)
            return

        # Safety: default is IDE chat. Shell execution requires explicit /sh prefix.
        if command_text.startswith("/sh "):
            shell_text = command_text.replace("/sh ", "", 1).strip()
            if not shell_text:
                raise ValueError("Usage: /sh [shell command]")
            out = run_shell_command(command_id, shell_text)
            update_command(command_id, "completed", response_log=out)
            return

        # Optional routing: "@ag " / "@vscode " / "@cursor " prefix.
        q = command_text
        target = IDE_TARGET
        for prefix, t in (("@ag ", "antigravity"), ("@antigravity ", "antigravity"), ("@vscode ", "vscode"), ("@cursor ", "cursor")):
            if q.lower().startswith(prefix):
                q = q[len(prefix) :].lstrip()
                target = t
                break

        # For now, target selection only changes which window title you configure in .env.
        # You can run multiple agents with different IDE_WINDOW_TITLE_SUBSTR + IDE_TARGET if needed.
        _ = target  # reserved for future per-target profiles.
        result = ide_chat_via_gui(q)
        update_command(command_id, "completed", response_log=result["log"], image_url=result["image_url"])

    except Exception as exc:
        logger.exception("Command failed: %s", command_id)
        update_command(command_id, "error", response_log=str(exc))


def bootstrap_pending_commands() -> None:
    query = (
        supabase.table("commands")
        .select("id,user_id,command_text,status")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(50)
    )

    if AGENT_USER_ID:
        query = query.eq("user_id", AGENT_USER_ID)

    response = query.execute()

    rows = response.data or []
    if rows:
        logger.info("Found %d pending command(s) on startup", len(rows))
    for row in rows:
        handle_command(row)


def start_realtime_listener() -> None:
    # supabase-py realtime channels are async-only. The sync client raises:
    # NotImplementedError: "available in the sync client ... async client only"
    #
    # For MVP reliability on Windows, we poll pending commands instead.
    logger.info(
        "Realtime listener disabled (sync client). Polling pending commands every %.2fs",
        POLL_INTERVAL_SEC,
    )


def poll_pending_commands_forever() -> None:
    while True:
        try:
            query = (
                supabase.table("commands")
                .select("id,user_id,command_text,status")
                .eq("status", "pending")
                .order("created_at", desc=False)
                .limit(POLL_MAX_BATCH)
            )

            if AGENT_USER_ID:
                query = query.eq("user_id", AGENT_USER_ID)

            response = query.execute()
            rows = response.data or []
            for row in rows:
                handle_command(row)
        except Exception:
            logger.exception("Polling loop error")

        time.sleep(POLL_INTERVAL_SEC)


def main() -> None:
    bootstrap_pending_commands()
    start_realtime_listener()
    poll_pending_commands_forever()


if __name__ == "__main__":
    main()

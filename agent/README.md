# Server Vibe - Python Agent (Step 2)

## 1) Setup
```powershell
cd agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Fill `.env` with your Supabase values.  
Optional: set `AGENT_USER_ID` to process only one user's commands.

## 2) Run
```powershell
python main.py
```

## 3) Command format
- Default: natural-language message is sent to the IDE chat via GUI automation and the latest AI reply is copied back.
- Special commands:
  - `/capture`
  - `/open chrome` (chrome, vscode, notepad, explorer, terminal, powershell)
  - `/sh ...` (explicit shell command execution)
  - `@ag ...` / `@vscode ...` (optional routing prefix; window targeting is controlled via `.env`)

## Notes
- Use `service_role` only in a trusted local environment.
- Screenshot path format: `screenshots/{user_id}/{timestamp}.png`.

## IDE GUI Automation (.env)
Required:
- `IDE_WINDOW_TITLE_SUBSTR` (e.g. `Visual Studio Code`, `Cursor`, `Antigravity`)

Optional:
- `IDE_OPEN_CHAT_HOTKEY` (open chat panel)
- `IDE_CHAT_FOCUS_HOTKEY` (focus chat input)
- `IDE_FOCUS_TRANSCRIPT_HOTKEY` (focus transcript/log area)
- `IDE_COPY_TRANSCRIPT_HOTKEY` (copy transcript; if unset, uses Ctrl+A then Ctrl+C)
- `IDE_INPUT_IMAGE` / `IDE_OUTPUT_IMAGE` (template images to click instead of hard-coded coordinates)
- `IDE_IMAGE_TIMEOUT_SEC`
- `IDE_INPUT_POS` / `IDE_OUTPUT_POS` (last-resort coordinates)
- `IDE_RESPONSE_WAIT_SEC` (default `15`)
- `AI_ANSWER_MARKERS` (comma-separated markers for parsing the last assistant answer)

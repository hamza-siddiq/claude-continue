# claude-continue

macOS CLI tool that continues Claude Desktop **Code** or **Chat** sessions on a schedule. When a session time limit is reached, run this tool at a clock time you choose—it activates Claude, switches to the right tab, opens the first chat under **Recents** (skipping **Pinned**), types `continue`, and presses Enter.

## Requirements

- macOS 13+
- Python 3.10+
- [Claude Desktop](https://claude.ai/download) installed at `/Applications/Claude.app`
- **Accessibility** permission for the terminal running this tool (Terminal, iTerm, or Cursor)

## Install

```bash
cd /Users/hamza/Documents/Projects/GitHub/claude-continue
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Permissions

1. Open **System Settings → Privacy & Security → Accessibility**
2. Enable your terminal app (e.g. Terminal, iTerm, or Cursor)
3. On first run, macOS may ask to allow controlling **Claude**—allow it

### Verify

With Claude open:

```bash
claude-continue inspect --depth 6
```

You should see elements with titles like `Code`, `Chat`, `Recents`, and optionally `Pinned` in the output.

## Usage

Run immediately (for testing):

```bash
claude-continue continue --now          # Code tab (default)
claude-continue continue code --now
claude-continue continue chat --now
```

Wait until a clock time, then run once:

```bash
claude-continue continue --at "4:20pm"
claude-continue continue code --at "7:30 am"
claude-continue continue chat --at "16:20"
```

`--at` uses **minute precision** (seconds are ignored). Schedule at least one minute ahead of the current time.

If the time has already passed today, the tool waits until **the same time tomorrow**. Use `--today-only` to fail instead:

```bash
claude-continue continue --at "4:20pm" --today-only
```

Debug the UI tree:

```bash
claude-continue inspect --depth 8
```

## What it does (continue mode)

1. Launch and focus Claude Desktop
2. Switch to **Code** or **Chat** via the top nav pills (if you are on another tab)
3. Skip any **Pinned** chats above **Recents**; click the first chat **below** the Recents heading
4. Type `continue` in the tab’s composer and press Enter
   - **Code:** **Prompt** field
   - **Chat:** “Write your prompt…” field

## Limitations

- UI labels must match the English Claude app (`Code`, `Chat`, `Recents`, `Pinned`)
- Claude UI updates may break element matching—use `inspect` to tune selectors
- Automation is inherently fragile; test with `--now` before relying on a schedule
- Cowork tab is not supported yet

## License

MIT

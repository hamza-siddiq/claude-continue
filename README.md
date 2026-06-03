# claude-continue

macOS CLI tool that continues Claude Desktop **Code** or **Chat** sessions when usage limits are reached. It reads **Settings → Usage** to decide when to run, opens the first chat under **Recents** (skipping **Pinned**), types `continue`, and presses Enter.

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

## Usage

### Automatic scheduling (default)

With no flags, the tool opens the bottom sidebar menu → **Settings** → **Usage**, then:

| Usage state | When it runs continue |
|-------------|------------------------|
| **All models** at 100% | At the reset clock time (e.g. `Resets Wed 12:00 PM`) |
| **Current session** at 100% (all models not full) | Countdown + 1 minute (e.g. `Resets in 3 hr 53 min` → run in 3 hr 54 min) |
| Neither at 100% | Asks whether to run now |

At the scheduled time, continue is sent **up to 3 times**: immediately, then after **30 seconds**, then after **1 more minute** (~90s from the first try), stopping early if a attempt succeeds.

```bash
claude-continue code
claude-continue chat
```

### Manual time override

```bash
claude-continue code --at "4:20pm"
claude-continue chat --at "7:30 am"
```

`--at` uses **minute precision**. If that time already passed today, it waits until the same time **tomorrow**.

### Debug

```bash
claude-continue inspect --depth 10
claude-continue inspect --sidebar
claude-continue inspect --usage
```

## What it does

1. Launch and focus Claude Desktop
2. Open **Settings → Usage** (via the bottom sidebar menu) unless `--at` is set
3. Schedule from usage bars, or use `--at`
4. Switch to **Code** or **Chat**
5. Click the first chat below **Recents** (skip **Pinned**)
6. Type `continue` and press Enter

## Limitations

- English UI labels (`Settings`, `Usage`, `Recents`, etc.)
- Usage layout must match what Claude Desktop exposes to Accessibility
- Fragile if Claude changes UI—use `inspect` to debug
- Cowork tab not supported

## License

MIT

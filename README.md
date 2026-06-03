# claude-continue

**Automatically send `continue` in Claude Desktop when your usage limit resets.**

A macOS CLI that reads **Settings → Usage**, waits until the right moment, then opens your first **Recents** chat on the **Code** or **Chat** tab and submits `continue`—so you do not have to babysit the reset clock.

```bash
claude-continue code    # Code tab
claude-continue chat    # Chat tab
```

---

## Table of contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install](#install)
- [Permissions](#permissions)
- [Usage](#usage)
- [Scheduling logic](#scheduling-logic)
- [Sleep and power](#sleep-and-power)
- [UI reference](#ui-reference)
- [Debugging](#debugging)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Development](#development)
- [License](#license)

---

## How it works

```mermaid
flowchart LR
  A[Start CLI] --> B{--at set?}
  B -->|No| C[Open Settings → Usage]
  B -->|Yes| D[Parse clock time]
  C --> E[Read usage bars]
  E --> F[Compute run time]
  D --> F
  F --> G[Wait until scheduled time]
  G --> H[Launch Claude]
  H --> I[Code or Chat tab]
  I --> J[First chat under Recents]
  J --> K["Type continue + Enter"]
  K --> L{Success?}
  L -->|No| M[Retry up to 3×]
  L -->|Yes| N[Done]
  M --> K
```

1. **Schedule** — From the Usage page (or `--at`), decide when to run.
2. **Wait** — Sleep in short chunks; the Mac may sleep; energy-friendly wake hints when far away.
3. **Continue** — Focus Claude, switch tab, open the first chat below **Recents** (skip **Pinned**), send `continue`, retry if needed.

Claude can be closed during the wait. The tool launches and focuses it at run time.

---

## Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | macOS 13 (Ventura) or later |
| **Python** | 3.10+ |
| **App** | [Claude Desktop](https://claude.ai/download) at `/Applications/Claude.app` |
| **Permission** | **Accessibility** for the terminal running this tool (Terminal, iTerm, Cursor, etc.) |

---

## Install

```bash
git clone https://github.com/hamza-siddiq/claude-continue.git
cd claude-continue

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify:

```bash
claude-continue --version
```

---

## Permissions

1. **System Settings → Privacy & Security → Accessibility** — enable your terminal app.
2. On first run, macOS may prompt to allow controlling **Claude** — choose **Allow**.

Without Accessibility, the tool cannot read the UI or send keystrokes.

---

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `claude-continue code` | Schedule from Usage (or `--at`), then continue on the **Code** tab |
| `claude-continue chat` | Same for the **Chat** tab |
| `claude-continue inspect` | Dump the accessibility tree for debugging |

### Options

| Flag | Commands | Description |
|------|----------|-------------|
| `--at TIME` | `code`, `chat` | Skip Usage; run at a clock time, e.g. `"4:20pm"`, `"7:30 am"`, `"16:20"` |
| `--version` | all | Print version and exit |

`--at` uses **minute precision**. If that time already passed today, the tool waits until the same time **tomorrow**.

### Examples

```bash
# Read Usage, wait for reset, continue Code session
claude-continue code

# Continue Chat when session countdown ends
claude-continue chat

# Run at a specific time (ignore Usage)
claude-continue code --at "12:00pm"
claude-continue chat --at "7:30 am"

# Keep running after you close the terminal window (optional)
nohup claude-continue code >> ~/claude-continue.log 2>&1 &
```

### What you will see

Typical output when limits are active:

```text
Usage: all_models=100%, session=ok
  All models reset: Resets Wed 12:00 PM
Scheduled for 2026-06-04 12:00 PM
Closed Settings.
Scheduled system wake in 2 hr 58 min (Mac may sleep until then).
Scheduled time reached.
Continue attempt 1/3...
```

If usage is **not** at 100%, the tool asks:

```text
Usage is not at 100%. Run continue now? [y/N]:
```

---

## Scheduling logic

With no `--at`, the tool opens **Settings** (**⌘,**), selects **Usage** in the **main** settings nav (not **Desktop app → General**), reads the usage bars, then closes Settings.

| Usage state | When `continue` runs |
|-------------|----------------------|
| **All models** at 100% | At the reset **clock** time (e.g. `Resets Wed 12:00 PM`) |
| **Current session** at 100% (all models not full) | Countdown **+ 1 minute** (e.g. `Resets in 3 hr 53 min` → run in 3 hr 54 min) |
| Neither at 100% | Prompts: run now or cancel |

### Retries at run time

At the scheduled time, the tool sends `continue` **up to 3 times**:

| Attempt | When |
|---------|------|
| 1 | Immediately |
| 2 | 30 seconds later |
| 3 | 60 seconds after attempt 2 (~90s after the first) |

Stops early if an attempt succeeds.

---

## Sleep and power

The tool **does not** keep your Mac awake for the entire wait.

| Phase | Behavior |
|-------|----------|
| **Long wait** (30+ min away) | Best-effort `pmset relative wake` so the Mac can sleep and wake shortly before the run |
| **Last ~3 minutes** | `caffeinate` so an **already-awake** Mac does not idle-sleep and miss the minute |
| **After system sleep** | When the Mac wakes, the CLI resumes; if the scheduled time already passed, it runs immediately |

**Claude does not need to stay open** while waiting. After reading Usage, Settings is closed; at run time Claude is launched in the **foreground** for reliable automation.

**Keep the terminal session alive** — if your shell or laptop policy kills background jobs on sleep, use `nohup` or leave the lid open / plugged in for critical resets. Lid-closed sleep on battery may skip a scheduled wake.

---

## UI reference

Claude Desktop layout this tool expects:

| Screenshot | Shows |
|------------|--------|
| [Home.png](Home.png) | Home screen with usage banner (`Usage limit reached • Resets …`) |
| [Settings.png](Settings.png) | Settings after **⌘,** — **Usage** in the upper nav (General … Billing → **Usage** → Capabilities …), above **Desktop app** |

The automation always uses **⌘,** then **Usage** in that upper list — not the second **General** under **Desktop app**.

---

## Debugging

```bash
# Full accessibility tree (default depth 6)
claude-continue inspect --depth 10

# Sidebar chat rows (Recents selection)
claude-continue inspect --sidebar

# Settings sidebar nav targets
claude-continue inspect --settings-nav

# Open Usage and print detected limits
claude-continue inspect --usage
```

Use these when Anthropic ships a UI change and selectors stop matching.

---

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| **Permission errors** | Re-enable Accessibility for your terminal; restart the terminal after changing settings |
| **Claude not found** | Install Claude Desktop; confirm `/Applications/Claude.app` exists |
| **No chats under Recents** | Open the Code or Chat tab manually once so Recents is populated |
| **Wrong tab or chat** | Run `claude-continue inspect --sidebar`; check English UI labels |
| **Missed reset after sleep** | Ensure the CLI process is still running; prefer plugged-in / lid open; check logs if using `nohup` |
| **Nothing happens until I click Claude** | Update to latest build (foreground launch at continue time); grant Automation permission for Claude |

---

## Limitations

- **English UI** — expects labels like `Settings`, `Usage`, `Recents`, `Code`, `Chat`
- **Usage layout** — depends on what Claude Desktop exposes to Accessibility
- **UI changes** — fragile across app updates; use `inspect` to adapt
- **Cowork tab** — not supported (Code and Chat only)

---

## Development

```bash
source .venv/bin/activate
pip install -e .

# Run unit tests
python -m unittest discover -s tests -q
```

Project layout:

```text
src/claude_continue/
  cli.py              # Entry point
  usage_ui.py         # Settings → Usage navigation
  usage_parse.py      # Reset time / countdown parsing
  schedule.py         # Wait until target time
  power.py            # Sleep / wake / caffeinate helpers
  claude_app.py       # Tab, Recents, composer automation
tests/
```

---

## License

MIT

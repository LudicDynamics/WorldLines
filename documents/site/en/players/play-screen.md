---
title: "The play screen"
description: "What you see, click and press on the web and in the terminal."
---

<!-- section: open -->
## Web: start a run

On the overview, click a world and its card slides out: start a new run there, or continue one from its list of saves. The run opens on the play page (called "test bench" in the top bar): the conversation on the left, your state and the characters present on the right.

<!-- section: read -->
## Web: what you see in the conversation

- **Two beats, two colors**: planning is green, resolve is red. What the beats are: [How a turn works](/docs/players/how-to-play).
- **Streaming prose**: the host and each character get their own blocks, so who is talking is clear.
- **Dice cards**: one per check, with the skill, target, roll and outcome (critical / success / failure / fumble).
- **State changes**: wounds, sanity loss, items, new places … as small chips under the beat.
- **Settling**: after the prose, the engine still checks, writes and lets characters react; for those seconds you see "settling" with a timer — it is not stuck.
- **Background check**: after a beat you may see "checking this beat's state in the background…", followed by "state checked: no change" or "state corrected after a closer look" with what changed.
- **Your state**: health, sanity and conditions (e.g. poisoned, 2 turns left) on the right.
- **The ending**: reach an ending and you get an illustrated card: the ending's name, the truth, and what this run gave you.

<!-- section: control -->
## Web: controls

- **Stop**: while a turn runs, the send button turns into "■ Stop"; the engine stops after the current step.
- **Scroll up**: reading back doesn't snap you to the bottom; "↓ Latest" brings you back.
- **Right panel**: "Player" shows your state, "Characters" what the people present are thinking.
- **Settings**: "⚙" at the top right — change the model, keys and language.
- **Hub**: "Hub ↗" in the top bar opens the Hub, with the worlds and characters online.

<!-- section: tui -->
## Terminal: in a run

In the terminal a run is one conversation with an input box at the bottom.

- **`/status`**: a panel of tabs you switch with ← / →: you, each character present, usage. Open a page directly with `/status plan` (the planning board), `/status dice` (recent rolls), `/status settlement` (ending and settlement), `/status account` (your account and who is judging).
- **Completion**: `/` lists commands and this world's skills (with values and descriptions); `@` completes names; `#` inside a sentence completes places and items.
- **Shortcut bar**: a row of buttons above the input box with the lines and commands you are most likely to need right now.
- **`/who`**: step into a character's view — where they are, what they remember, what they did in the last few turns.
- **Background check**: as on the web, the result shows after the beat.

Every command: [Terminal commands](/docs/players/commands).

<!-- section: keys -->
## Terminal: keys

| Key | Does |
|---|---|
| `Ctrl+K` / `Ctrl+P` | command palette |
| `Ctrl+L` | switch layers: prose only / prose with chips / plus the tool-call trace |
| `F6` | copy the whole conversation |
| `Ctrl+Q` | quit |

In the launcher: arrow keys or `Tab` to move, `Enter` to confirm, `r` resume, `c` continue a save, `n` new run, `s` settings, `Esc` quit.

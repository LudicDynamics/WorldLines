---
name: discord-bootstrap
description: Guide the user through connecting a NeonRP project to Discord — bot token setup, channel binding, and verifying the bridge works. Phase 0: scaffold only (no active bridge code yet). The detailed integration plan is tracked against ../buddy-bot.
---

# Discord Bootstrap (Phase 0)

L14 treats Discord as part of onboarding, not a separate product surface.
This skill documents what a Discord-aware NeonRP project should have
configured, so the user can come back and complete the connection when
bridge code lands.

# Current scope (Phase 0)

- Collect `discord.bot_token` and `discord.channel_id` from the user
  and store them in `~/.neonrp/config.json` under a top-level
  `"discord"` key.
- Do NOT actually connect. The bridge runtime is still in `../buddy-bot`
  and has not been integrated.
- Surface connection status in the TUI inline metadata area as
  `discord:pending` when the keys are present but bridge is unbuilt.

# User config keys

```json
{
  "discord": {
    "bot_token": "xxxxx.yyyyy.zzzzz",
    "channel_id": "1234567890",
    "guild_id": "9876543210",
    "relay_mode": "mirror",
    "connected": false,
    "last_check": null
  }
}
```

- `relay_mode`: one of `mirror` (push transcript to Discord),
  `input-only` (read commands from Discord), `bidirectional`.
- `connected`: updated by the bridge when it successfully attaches.
- `last_check`: ISO timestamp of the most recent handshake.

# What this skill should do

1. If `~/.neonrp/config.json.discord` already has `bot_token`, confirm
   with the user before overwriting.
2. Walk the user through creating a Discord Application + Bot at
   `https://discord.com/developers/applications`.
3. Ask for required permissions (at minimum: Read Messages, Send
   Messages, View Channel).
4. Collect `bot_token`, `channel_id`, and optionally `guild_id`.
5. Save to user config.
6. Print the OAuth invite URL the user should paste into their browser
   to add the bot to their server.
7. Leave `connected = false` — Phase 1 bridge will flip it.

# What this skill must NOT do

- Do NOT attempt to log in to Discord from this skill — there is no
  bridge client yet.
- Do NOT send messages to channels.
- Do NOT store the bot token anywhere other than
  `~/.neonrp/config.json` (never in project files or env files).

# Inline metadata contract

When the TUI renders the connection-state segment:

- No `bot_token` configured → `discord:off`
- `bot_token` set, `connected = false` → `discord:pending`
- `bot_token` set, `connected = true` → `discord:on`

# Handoff to Phase 1

When the bridge lands (tracked in `../buddy-bot`), Phase 1 will:

1. Read the same config keys.
2. Establish a gateway connection on TUI launch.
3. Flip `connected = true` and set `last_check`.
4. Route transcript events according to `relay_mode`.

The keys and file layout defined above are the stable contract; Phase 1
must not change them.

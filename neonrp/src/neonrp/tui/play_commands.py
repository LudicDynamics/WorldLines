"""Slash commands for the two-beat play (TUI step 3, 10-08). Each reads the engine or the session's BeatState and
writes into the conversation; nothing here changes the world except /rollback, /lang and /beats (said so on screen).

    /status [player|agents]   the right column on that view, and the same in the transcript
    /status plan              the planning board, the agreed checks, who holds the mic
    /status dice [n]          the last n dice this session rolled (default 10)
    /status settlement        the run's ending card (once it has settled)
    /status contract          the play contract this run was built under (what kind of game, how a turn runs)
    /status account           the Worldlines account (/login) and who judges the talk (Jev)
    /lang [zh|en|ja|ko]       the language this run is narrated in
    /undo list · /undo <turn> list the turns of this line / fork a new line at that turn (plain /undo as before)
    /dev graph                the orchestration graph in effect (beats · layers · edges · lint)
    /dev dry-run <line>       one beat through a throwaway copy of the run — nothing is kept (calls the model)
    /dev beats [on|off]       write the beat skeleton into the prose as text too (headless / debugging)
    /dev template [id]        the templates on the shelf (with their contract), or one in detail
    /dev validate · mcp · bridge · debug [on|off|status]   troubleshooting / integration (kept from the retired table)
    /status usage             the conversation's messages and tokens
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from rich.panel import Panel
from rich.text import Text

from neonrp.tui import beats as B
from neonrp.tui.i18n import get_message

MUTED = "#9ca3af"


def _m(app: Any, key: str, **kw: Any) -> str:
    s = get_message(getattr(app, "ui_locale", "zh") or "zh", f"pc.{key}")
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def _view(app: Any) -> Any:
    from neonrp.tui.app import ConversationView

    return app.query_one("#conversation-view", ConversationView)


def _say(app: Any, text: str, style: str = MUTED) -> None:
    _view(app).add_beat_row(Text(text, style=style), "pc-out")


def _run_root(app: Any) -> Any:
    """The run's folder: the session's, else the app's."""
    return getattr(getattr(app, "session", None), "root", None) or getattr(app, "root", None)


def _state(app: Any) -> B.BeatState:
    st = getattr(app, "_beat_state", None)
    if st is None:
        st = app._beat_state = B.BeatState()
    return st


# ── reads ────────────────────────────────────────────────────────────────────

def cmd_plan(app: Any, args: list[str]) -> None:
    st = _state(app)
    row = B.plan_text({"board": st.board, "checks": st.checks, "mic": st.mic})
    if row is None:
        _say(app, _m(app, "plan.none"))
    else:
        _view(app).add_beat_row(row, "beat-plan")
    from neonrp.tui import status_side as S

    if S.judge_matters(_run_root(app)):  # the board settles by the judge — say who, only while planning runs
        _view(app).add_beat_row(S.judge_line(getattr(app, "ui_locale", "zh") or "zh"), "pc-status")


def cmd_dice(app: Any, args: list[str]) -> None:
    from neonrp.core import beat_display as _bd
    from neonrp.tui.app import ConversationView

    n = int(args[0]) if args and args[0].isdigit() else 10
    rolls = _state(app).dice[-n:]
    if not rolls:
        _say(app, _m(app, "dice.none"))
        return
    for d in rolls:
        line = _bd._dice_line(d, _bd._lang(app.root)) if d.get("total") is not None else None
        w = ConversationView._build_dice_widget(line, level=_bd.outcome_level(d)) if line else None
        _view(app).add_beat_row(w if w is not None else B.tool_text(d), "beat-dice")


def cmd_status(app: Any, args: list[str]) -> None:
    from neonrp.tui import status_side as S

    which = "agents" if args and args[0].lower() in ("agents", "agent", "a", "角色") else "player"
    try:
        side = app.query_one("#status-side", S.StatusSide)
        side.refresh_state()
        side.show(which)
        data, life = side.data, side.lifecycle
    except Exception:  # noqa: BLE001 — no column (build mode): still answer in the transcript
        data, life = S.collect(app.root), {}
    loc = getattr(app, "ui_locale", "zh") or "zh"
    body = S.render_agents(loc, data.get("agents") or [], life) if which == "agents" else S.render_player(loc, data.get("player") or {})
    _view(app).add_beat_row(body, "pc-status")


def cmd_settlement(app: Any, args: list[str]) -> None:
    st = app._settlement_now() if hasattr(app, "_settlement_now") else {}
    if not st or not st.get("exit"):
        _say(app, _m(app, "settle.none"))
        return
    _view(app).add_beat_row(B.settlement_text(st, getattr(app, "ui_locale", "zh") or "zh"), "beat-settlement")


def cmd_contract(app: Any, args: list[str]) -> None:
    t = contract_text(app)
    if t is None:
        _say(app, _m(app, "contract.none"))
        return
    _view(app).add_beat_row(t, "pc-contract")


def contract_text(app: Any) -> Text | None:
    from neonrp.template.contract import run_contract

    c = run_contract(app.root) if app.root else None
    if not c:
        return None
    t = Text()
    t.append(f"{c.get('_ref') or (str(c.get('id')) + '@' + str(c.get('version')))}  ", style=f"bold {B.SETTLE_COLOR}")
    t.append(str(c.get("title") or ""), style="#f8fafc")
    if c.get("pitch"):
        t.append(f"\n{c['pitch']}", style=MUTED)
    for key in ("entry", "exit", "endings", "deaths", "engine"):
        if c.get(key):
            t.append(f"\n{key:8}", style="#60a5fa")
            t.append(json.dumps(c[key], ensure_ascii=False)[:160], style="#d1d5db")
    return t


def cmd_template(app: Any, args: list[str]) -> None:
    from neonrp import template as TP

    found = TP.discover()
    if not args:
        t = Text()
        for tid, d in sorted(found.items()):
            try:
                tt = TP.load(d)
                title, contract = str((tt.card or {}).get("title") or tid), tt.play_contract
            except Exception:  # noqa: BLE001
                title, contract = tid, ""
            t.append(f"{tid:28}", style="bold #f8fafc")
            t.append(f" {title}", style="#d1d5db")
            if contract:
                t.append(f"  [{contract}]", style=B.SETTLE_COLOR)
            t.append("\n")
        t.append(_m(app, "template.hint"), style=MUTED)
        _view(app).add_beat_row(t, "pc-template")
        return
    tid = args[0].removeprefix("tpl:")
    if tid not in found:
        _say(app, _m(app, "template.unknown", id=tid), style="#f87171")
        return
    tt = TP.load(found[tid])
    rep = TP.lint(tt)
    counts: dict[str, int] = {}
    for p in rep.get("problems") or []:
        counts[p["level"]] = counts.get(p["level"], 0) + 1
    t = Text()
    t.append(f"{tid}  ", style="bold #f8fafc")
    t.append(str((tt.card or {}).get("title") or ""), style="#d1d5db")
    if (tt.card or {}).get("pitch"):
        t.append(f"\n{tt.card['pitch']}", style=MUTED)
    t.append(f"\npack {tt.pack_name}", style="#60a5fa")
    if tt.play_contract:
        t.append(f" · {tt.play_contract}", style=B.SETTLE_COLOR)
    t.append("\nlint " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())) + ("  ✓" if rep.get("publishable") else ""),
             style="#4ade80" if rep.get("publishable") else "#fbbf24")
    t.append(f"\n{_m(app, 'template.open', id=tid)}", style=MUTED)
    _view(app).add_beat_row(t, "pc-template")


def cmd_graph(app: Any, args: list[str]) -> None:
    from neonrp.core import orchestration

    g = orchestration.graph(app.root)
    body = Text(orchestration.describe(g), style="#d1d5db")
    for x in g.get("lint") or []:
        body.append(f"\n⚠ {x.get('code')}  {x.get('msg')}", style="#fbbf24")
    _view(app).add_beat_row(Panel(body, title="[bold #60a5fa]orchestration[/]", title_align="left", border_style="#60a5fa", expand=False),
                           "pc-graph")


# ── writes / runs ────────────────────────────────────────────────────────────

def cmd_dry_run(app: Any, args: list[str]) -> None:
    text = " ".join(args).strip()
    if not text:
        _say(app, _m(app, "dry.usage"), style="#f87171")
        return
    _say(app, _m(app, "dry.start"))

    def work() -> None:
        from neonrp.core import dry_run

        try:
            res = dry_run.run(app.root, text, provider=getattr(app, "provider", None))
        except Exception as exc:  # noqa: BLE001
            res = {"error": str(exc)[:200]}
        app.call_from_thread(_show_dry, app, res)

    app.run_worker(work, thread=True, exclusive=False, group="dry-run")


def _show_dry(app: Any, res: dict[str, Any]) -> None:
    if res.get("error"):
        _say(app, f"✕ {res['error']}", style="#f87171")
        return
    t = Text()
    for tr in res.get("traces") or []:
        ap = tr.get("apply") or {}
        kind = str((ap.get("beat") or {}).get("kind") or "resolve")
        t.append(f"── {kind} ──\n", style=f"bold {B.color_of('plan' if kind in ('plan', 'opening') else kind)}")
        t.append(str(ap.get("narration_plain") or "")[:400] + "\n", style="#d1d5db")
        ch = B.change_text({"applied": ap.get("applied") or [], "created": ap.get("created") or [], "refused": ap.get("refused") or []})
        if ch is not None:
            t.append_text(ch)
            t.append("\n")
    t.append(_m(app, "dry.kept"), style=MUTED)
    _view(app).add_beat_row(Panel(t, title="[bold #a78bfa]dry-run[/]", title_align="left", border_style="#a78bfa", expand=False), "pc-dry")


def cmd_rollback(app: Any, args: list[str]) -> None:
    from neonrp.core import rollback as R
    from neonrp.webui.commit_routes import commit_graph

    g = commit_graph(app.root)
    branch = str(g.get("branch") or "main")
    if not args:
        mine = sorted((n for n in g.get("nodes") or [] if str(n.get("branch") or "main") == branch and n.get("turn_seq") is not None),
                      key=lambda n: n["turn_seq"])
        if not mine:
            _say(app, _m(app, "rollback.none"))
            return
        t = Text(f"{branch}\n", style="bold #f8fafc")
        for n in mine[-15:]:
            t.append(f"  {n['turn_seq']:>3}  ", style="#60a5fa")
            t.append(f"{str(n.get('label') or '')[:50]}\n", style="#d1d5db")
        t.append(_m(app, "rollback.hint"), style=MUTED)
        _view(app).add_beat_row(t, "pc-rollback")
        return
    if not args[0].isdigit():
        _say(app, _m(app, "rollback.usage"), style="#f87171")
        return
    cid = R.commit_for_turn(app.root, int(args[0]), branch)
    if cid is None:
        _say(app, _m(app, "rollback.unknown", turn=args[0]), style="#f87171")
        return
    res = R.rollback(app.root, cid, branch)
    if not res.get("ok"):
        _say(app, f"✕ {res.get('error')}", style="#f87171")
        return
    app.branch = res["branch"]
    app._beat_state = None
    app._init_session()  # the next turn runs on the new line
    _say(app, _m(app, "rollback.done", turn=res.get("turn_seq"), branch=res["branch"]), style="#4ade80")
    try:
        from neonrp.tui.status_side import StatusSide

        app.query_one("#status-side", StatusSide).refresh_state()
    except Exception:  # noqa: BLE001
        pass


def cmd_lang(app: Any, args: list[str]) -> None:
    from neonrp.core.output_lang import ALL_LANGS, prompt_lang, write_output_lang

    if not args:
        _say(app, _m(app, "lang.now", lang=prompt_lang(app.root), all=" · ".join(ALL_LANGS)))
        return
    lg = args[0].lower()[:2]
    if lg not in ALL_LANGS:
        _say(app, _m(app, "lang.usage", all=" · ".join(ALL_LANGS)), style="#f87171")
        return
    write_output_lang(app.root, lg)
    _say(app, _m(app, "lang.set", lang=lg), style="#4ade80")


def cmd_beats(app: Any, args: list[str]) -> None:
    from neonrp.core import beat_display
    from neonrp.core.paths import get_data_dir_name

    if not args:
        _say(app, _m(app, "beats.now", state="on" if beat_display.enabled(app.root) else "off"))
        return
    on = args[0].lower() in ("on", "1", "true", "开")
    p = Path(app.root) / get_data_dir_name(Path(app.root)) / "meta" / "engine.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        d = {}
    d.setdefault("turn", {}).setdefault("display", {})["beats"] = "on" if on else "off"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    _say(app, _m(app, "beats.set", state="on" if on else "off"), style="#4ade80")


# ── /status as tabs (10-23): 玩家 · one per character · 用量 (account, contract, board, dice, ending, tokens) ─────

USAGE_SUBS = ("plan", "board", "dice", "rolls", "settlement", "end", "ending", "contract", "account", "login", "jev",
              "usage", "stats")


def status_tabs(app: Any) -> list[tuple[str, str]]:
    """[(key, label)]: the player, each character of the run (soul / the pack's cast), then usage."""
    from neonrp.tui import status_side as S

    root = _run_root(app)
    data = S.collect(root) if root else {"player": {}, "agents": []}
    p = data.get("player") or {}
    tabs = [("player", str(p.get("name") or _m(app, "tab.player")))]
    tabs += [(f"soul:{a['id']}", str(a.get("name") or a["id"])) for a in data.get("agents") or []]
    tabs.append(("usage", _m(app, "tab.usage")))
    return tabs


def status_body(app: Any, key: str) -> Any:
    """What one /status tab shows (a rich renderable)."""
    from neonrp.tui import status_side as S

    loc = getattr(app, "ui_locale", "zh") or "zh"
    root = _run_root(app)
    data = S.collect(root) if root else {"player": {}, "agents": []}
    if key == "player":
        from neonrp.tui import play_hints as H

        out = S.render_player(loc, data.get("player") or {})
        sheet = H.sheet_text(H.menu(root, ttl=0), loc)  # attributes · skills with value and line (10-23)
        if sheet is not None:
            out.append("\n")
            out.append_text(sheet)
        return out
    if key.startswith("soul:"):
        sid = key[len("soul:"):]
        life = dict(getattr(app, "_soul_status_snapshot", None) or {})
        return S.render_agents(loc, [a for a in data.get("agents") or [] if a.get("id") == sid], life)
    parts: list[Any] = [account_text(app)]

    def head(k: str) -> Text:
        return Text(f"\n{_m(app, k)}", style=f"bold {MUTED}")

    parts += [head("tab.contract"), contract_text(app) or Text(_m(app, "contract.none"), style=MUTED)]
    st = _state(app)
    plan = B.plan_text({"board": st.board, "checks": st.checks, "mic": st.mic})
    parts += [head("tab.plan"), plan if plan is not None else Text(_m(app, "plan.none"), style=MUTED)]
    parts.append(head("tab.dice"))
    if st.dice:
        from neonrp.core import beat_display as _bd

        for d in st.dice[-10:]:
            line = _bd._dice_line(d, _bd._lang(app.root)) if d.get("total") is not None else None
            parts.append(Text(str(line)) if line else B.tool_text(d))
            from neonrp.tui.play_hints import dice_detail

            why = dice_detail(d, loc)
            if why is not None:
                parts.append(why)
    else:
        parts.append(Text(_m(app, "dice.none"), style=MUTED))
    sett = app._settlement_now() if hasattr(app, "_settlement_now") else {}
    parts += [head("tab.settlement"),
              B.settlement_text(sett, loc) if sett and sett.get("exit") else Text(_m(app, "settle.none"), style=MUTED)]
    if hasattr(app, "_stats_markup"):
        parts += [Text(""), Text.from_markup(app._stats_markup())]
    out = Text()
    for i, part in enumerate(parts):
        if i:
            out.append("\n")
        out.append_text(part if isinstance(part, Text) else Text(str(part)))
    return out


def open_status(app: Any, key: str | None = None) -> bool:
    """The /status screen on tab ``key`` (or the one already open switches to it). False when the app is not running
    (tests, headless): the caller answers in the transcript as before."""
    if not getattr(app, "is_running", False):
        return False
    from neonrp.tui.status_screen import StatusScreen

    if isinstance(app.screen, StatusScreen):
        app.screen.show(key or "player")
    else:
        app.push_screen(StatusScreen(app, key or "player"))
    return True


# The live table stays small (≤ 25) — three top-level commands, the rest as their sub-items

def cmd_status_group(app: Any, args: list[str]) -> None:
    """/status [player | agents | plan | dice [n] | settlement | contract | account | usage | room …] — with nothing after
    the item, a screen of tabs (← / →); with more (dice 5, room invite …) the transcript as before."""
    sub = (args[0].lower() if args else "player")
    rest = args[1:]
    if not rest and sub not in ("room", "seats"):
        if sub in ("agents", "agent", "a"):
            souls = [k for k, _ in status_tabs(app) if k.startswith("soul:")]
            key = souls[0] if souls else "player"
        else:
            key = "usage" if sub in USAGE_SUBS else "player"
        if open_status(app, key):
            return
    if sub in ("plan", "board"):
        cmd_plan(app, rest)
    elif sub in ("dice", "rolls"):
        cmd_dice(app, rest)
    elif sub in ("settlement", "end", "ending"):
        cmd_settlement(app, rest)
    elif sub == "contract":
        cmd_contract(app, rest)
    elif sub in ("account", "login", "jev"):
        cmd_account(app, rest)
    elif sub in ("usage", "stats"):
        app._cmd_stats()  # the conversation's messages and tokens (the retired /stats)
    elif sub in ("room", "seats"):  # 10-10: the networked table — seats, invites, join requests
        from neonrp.tui import net_room

        net_room.cmd_room(app, rest)
    else:
        cmd_status(app, args)


def cmd_account(app: Any, args: list[str]) -> None:
    """/status account — the Worldlines account (/login) and who judges the talk (Jev): the two-beat play leans on it."""
    _view(app).add_beat_row(account_text(app), "pc-status")


def account_text(app: Any) -> Text:
    from neonrp.tui import status_side as S

    js = S.judge_status(getattr(app, "root", None))
    loc = getattr(app, "ui_locale", "zh") or "zh"
    t = Text(f"{_m(app, 'account.title')}  ", style="bold #f8fafc")
    t.append(_m(app, "account.in") if js["signed_in"] else _m(app, "account.out"), style="#4ade80" if js["signed_in"] else MUTED)
    t.append(f"\n{get_message(loc, 'account.hint')}", style=MUTED)  # how to sign in / out / switch (10-23)
    if S.judge_matters(_run_root(app)):  # who judges the talk — only where a planning node has talk to settle
        t.append("\n")
        t.append_text(S.judge_line(loc, js))
    return t


def cmd_dev(app: Any, args: list[str]) -> None:
    """/dev graph | dry-run <line> | beats [on|off] | template [id]"""
    sub = (args[0].lower() if args else "")
    rest = args[1:]
    fn = {"graph": cmd_graph, "dry-run": cmd_dry_run, "dryrun": cmd_dry_run, "beats": cmd_beats, "template": cmd_template,
          "templates": cmd_template,
          # The troubleshooting / integration ones kept from the retired table
          "validate": lambda a, r: a._forward_cli_command(_parsed("validate", r)),
          "mcp": lambda a, r: a._cmd_mcp(r), "bridge": lambda a, r: a._cmd_bridge(r),
          "debug": lambda a, r: a._cmd_verbose(r) if r else a._cmd_debug([]),  # one switch (debug was verbose's alias)
          }.get(sub)
    if fn is None:
        _say(app, _m(app, "dev.usage"), style="#f87171")
        return
    fn(app, rest)


def _parsed(cmd: str, args: list[str]) -> Any:
    from neonrp.tui.commands import parse_command

    return parse_command("/" + " ".join([cmd, *args]))


def undo_turn(app: Any, args: list[str]) -> bool:
    """/undo list · /undo <turn> → the turn list / a new line at that turn. False = plain /undo (the caller's old path)."""
    if not args:
        return False
    if args[0].lower() in ("list", "ls", "?"):
        cmd_rollback(app, [])
        return True
    if args[0].isdigit():
        cmd_rollback(app, args[:1])
        return True
    return False


PLAY_COMMANDS: dict[str, Callable[[Any, list[str]], None]] = {"status": cmd_status_group, "lang": cmd_lang, "dev": cmd_dev}

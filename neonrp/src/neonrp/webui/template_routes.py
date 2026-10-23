"""Templates over HTTP (neonrp/template, docs/TEMPLATE-PROTOCOL.md) — the web face of `neonrp template`.

Play (bound run):
    GET /api/v1/play/engine/template            card · mode · plot stages · ending; the reveal only after the ending
    GET /api/v1/play/engine/views               the declared views + panels bound to the run's current state (play3 right column)
    GET /api/v1/play/engine/world-data?name=economy|factions   the run's mixin world data (read-only)
    GET /api/v1/play/engine/graph               the orchestration graph in effect + the default one (core/orchestration, O1)
    GET /api/v1/play/engine/graph?template=<id> a template's graph without a session (the editor switches templates, 10-06)
    GET /api/v1/play/engine/hooks[?template=<id>]  what the editor picks from + each node's steps and settings (10-17 S1)
    POST /api/v1/local/templates/<id>/graph-lint {graph}   lint_runnable on a draft graph (the editor's unsaved edits, 10-07)
    POST /api/v1/local/templates/<id>/graph-test {lines, graph?}   the editor's chat test (10-17): core/graph_test in a child
                                                process — a stub model, a throwaway run; → steps · edges walked
    GET /api/v1/play/engine/contract            the play contract the run was built under, or {} (template/contract)
    GET /api/v1/play/engine/settlement          the run's settlement once it reached an exit, or {} (core/settlement, R5)
    GET /api/v1/play/engine/settlement/quiz     the sandbox mystery's 「真相三问」 once settled (core/truth_quiz; locked before)
    POST /api/v1/play/engine/settlement/quiz {answers}   grade once · three right → the reward soul with full memory ·
                                                 points pending, the fallback points when nobody came home (core/player_data rewards)
    GET /api/v1/play/engine/settlement/milestones   open-adventure milestones of this run (core/milestones)
    POST /api/v1/play/engine/settlement/leave   the player leaves: the milestones since the last leave settle (points · CG pending)
    GET /api/v1/play/engine/achievements        every achievement this run can unlock, unlocked or not (core/achievements)
    GET /api/v1/play/engine/beats?since=N       every beat event so far (core/beat_events; catch-up for the live log / a front end)
    GET /api/v1/play/engine/entities?cls=status one class's instances with their props (the play layer's conditions)
    GET /api/v1/play/engine/player-card         the character the player made (template/builder.py), values read back live; {} if none
    GET /api/v1/play/engine/sheet               the player's attributes / skills: label in the run's language · one-line desc · value (core/sheet)
    GET /api/v1/play/engine/actions             what the player can do now: world actions · skills · items · places · people · quick bar (core/play_menu)
    GET /api/v1/play/engine/objective           the stage's goal (reached stages only) · commissions (one state enum) · the run's exit in words
    GET /api/v1/play/engine/entities?clue=1[&cls=…]   only the clues (entry props.clue / class clue: true), found ones only
    GET /api/v1/play/engine/people              the people the player knows, as the player knows them (core/people; no persona / truths)
    GET /api/v1/play/engine/audio               what plays now: music · ambient bed · mood (the audio.cue shape) + the credits (core/audio)
    GET /api/v1/audio/<kind>/<id>.<hash>.mp3    a platform pool file (worldlines/audio): a year immutable when the hash is the file's;
                                                 Range requests answered (Safari / WKWebView stream media with them)
    GET /api/v1/play/engine/debug/entities?cls= one class's instances with ALL their props (the test bench; play reads keep people's to core/people.PLAY_PROPS)

    POST /api/v1/play/engine/choices {n?, avoid?}  a few more options for this moment → {lang, options, by: "more"}; read-only,
                                                 one model call on the run's provider; 409 while a turn runs (core/more_choices)
    GET /api/v1/play/engine/inspect?target=   one person / thing / place as the player knows it (core/inspect; no secrets)
    POST /api/v1/play/engine/inspect {target}  the same; a thing with no description gets one written (once per run, kept
                                                 in the run's entries overlay); while a turn runs: the read only (busy: true)
    POST /api/v1/report/ai {reason, excerpt, surface, turn?, soul?, msg_id?, note?, lang?}   report AI content → the platform
                                                 (core/ai_report; no session needed) · …/done {id} the page sent it itself
    POST /api/v1/play/engine/tick {turns: 1..50}   the world runs on its own (pack ticks + triggers, 0 token);
                                                 refused (409) while a turn is generating

Start a run:  POST /api/v1/play/session {slug: "tpl--<id>"}  (commands/web.py _switch_runtime)

Local (the template store: NEONRP_TEMPLATE_PATH + worldlines/templates from source; ids only, never paths):
    GET /api/v1/local/templates                 [{id, card, mode, pack, publishable, counts}]
    GET /api/v1/local/templates/<id>/lint       the full aggregated lint (Lint UI)
    GET /api/v1/local/templates/<id>/cover      the card's cover image (only a file inside the template)
    GET /api/v1/local/templates/<id>/contract[?fmt=ts|gd]       worldlines.contract/0.1 (or generated TS / GDScript)
    GET /api/v1/local/templates/<id>/assets                     image slots (cover · plot items/places/endings · souls)
    GET /api/v1/local/templates/<id>/audio?path=assets/audio/…&h=   a template's own audio file (immutable when h matches; Range)
    GET /api/v1/local/templates/<id>/assets/file?slot=…[&part=video]  a filled slot's image (a CG slot's video)
                                         [&variant=<sid>]  that companion's picture (default: the bound run's companion)
    POST /api/v1/local/templates/<id>/assets/upload?slot=…&ext=.png   raw image body (≤ 8 MB, PNG/JPEG/WebP)
    POST /api/v1/local/templates/<id>/assets/generate {slot, prompt?}  the configured image backend fills it
    GET /api/v1/local/templates/<id>/builder                    the player builder screen: declaration + companion candidates
    GET /api/v1/local/templates/<id>/builder/image?field=&option=   a portrait option's image · ?sid= a companion's portrait
    POST /api/v1/local/templates/<id>/builder/check {fields, companion}   {ok, errors} — the same check the run start does
    POST /api/v1/local/templates/<id>/builder/generate {field, fields, lang}   {text, source: model|example} — a text field the model writes
    (start with it: POST /api/v1/play/session {slug: "tpl--<id>", player: {fields, companion}})

Authoring (template/author.py — only templates under NEONRP_TEMPLATE_WRITE_DIR; built-ins are read-only, fork first):
    GET  /api/v1/local/templates/<id>/ui        {ui, writable, mixins, mixins_available, world_data}
    POST /api/v1/local/templates/<id>/fork      {id, title?}  → a new template in the write store
    POST /api/v1/local/templates/<id>/ops       {ops: [...]}  creator ops, all-or-nothing → {ok, applied, refused, lint, ui}
    (filled slot images are mirrored to $WORLDLINES_ASSETS_DIR/worlds/<id>/ when set)

Free zone (core/template_publish, 10-16 — the author's Worldlines account; nothing goes up before the checks pass):
    GET  /api/v1/local/templates/<id>/publish?lang=   {checks: {ok, problems}, work, signed_in}
    POST /api/v1/local/templates/<id>/publish {lang?, zone?} → {id, ref, zone, status, revision, message} · 401 · 403 · 409 · 422 {problems}
                                                 zone "curated" = the default zone's review queue (the web Hub desk)
    POST /api/v1/local/templates/<id>/publish {official: true, lang?}   「发布为官方」(10-17, the official account only):
         hub/template/<id> in the default zone, a new revision each time, the version must go up · 403 official_only ·
         409 official_version / official_id_taken (the dry run's ``official`` says whether this account may)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

_PLAY = "/api/v1/play/engine/template"
_TICK = "/api/v1/play/engine/tick"
_INSPECT = "/api/v1/play/engine/inspect"
_VIEWS = "/api/v1/play/engine/views"
_WDATA = "/api/v1/play/engine/world-data"
_RUNREADS = ("/api/v1/play/engine/graph", "/api/v1/play/engine/contract", "/api/v1/play/engine/settlement", "/api/v1/play/engine/beats", "/api/v1/play/engine/entities",
             "/api/v1/play/engine/player-card", "/api/v1/play/engine/sheet", "/api/v1/play/engine/actions",
             "/api/v1/play/engine/people", "/api/v1/play/engine/debug/entities",
             "/api/v1/play/engine/objective", "/api/v1/play/engine/settlement/quiz", "/api/v1/play/engine/settlement/milestones",
             "/api/v1/play/engine/achievements", "/api/v1/play/engine/audio")
WORLD_DATA = ("economy", "factions")  # mixin data the 3.0 screen needs (goods / markets / factions / colors); read-only
MAX_TICKS = 50
_LOCAL = "/api/v1/local/templates"
_AUDIO = "/api/v1/audio/"
TEMPLATE_VERSION = 1


def _orch_of(w: Any) -> str:
    """The orchestration preset a creator's work plays as (core/orch_presets), so a desk reopened elsewhere shows it."""
    from neonrp.core import orch_presets

    return orch_presets.default_for(w)


class TemplateRoutes:
    server: Any
    path: str

    def _send_media(self, p: Any, *, immutable: bool) -> None:
        """An audio file with Range support (Safari / WKWebView will not play media without it). ``immutable`` = the URL
        named the file's content hash: a year in the cache; otherwise the ETag revalidates."""
        import hashlib
        import mimetypes

        if p is None or not p.is_file():
            self.send_error(404)
            return
        st = p.stat()
        etag = '"' + hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()[:20] + '"'
        cache = "public, max-age=31536000, immutable" if immutable else "no-cache"
        size = st.st_size
        start, end = 0, size - 1
        rng = re.match(r"bytes=(\d*)-(\d*)$", (self.headers.get("Range") or "").strip())
        partial = bool(rng) and (rng.group(1) or rng.group(2)) != ""
        if partial:
            a, b = rng.group(1), rng.group(2)
            if a:
                start, end = int(a), min(int(b), size - 1) if b else size - 1
            else:
                start = max(0, size - int(b))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self._cors_headers()
                self.end_headers()
                return
        elif etag in [x.strip() for x in (self.headers.get("If-None-Match") or "").split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self._cors_headers()
            self.end_headers()
            return
        with p.open("rb") as fh:
            fh.seek(start)
            data = fh.read(end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _template_route_get(self, rt: Any) -> bool:
        route = urlparse(self.path).path.rstrip("/")
        if route == "/api/v1/play/engine/graph" and "template" in parse_qs(urlparse(self.path).query):
            # 10-06: a template's graph without a session — the orchestration editor switches between templates
            from neonrp.template import v3

            ref = parse_qs(urlparse(self.path).query)["template"][0]
            try:
                self._send_json(v3.graph_of(ref))
            except KeyError:
                self.send_error(404, "no such template")
            return True
        if route == "/api/v1/play/engine/hooks":
            # 10-17 第 4 批 S1: what the orchestration editor picks from — seams · handlers · triggers · ops · modes · ticks
            # (core/orchestration.hooks) and each node's steps with every setting's value now and its source (core/turn_steps);
            # ?template=<id> reads a template without a session, else the bound run
            from neonrp.core import orchestration as _orc, turn_steps
            from neonrp.template import v3

            q = parse_qs(urlparse(self.path).query)
            try:
                root = v3._graph_run(v3._template(q["template"][0])) if q.get("template") else (rt.root if rt is not None else None)
            except KeyError:
                self.send_error(404, "no such template")
                return True
            if root is None:
                self.send_error(409, "no play session")
                return True
            self._send_json({**_orc.hooks(root), "steps": turn_steps.describe(root, (q.get("lang") or [None])[0])})
            return True
        if route == _INSPECT:  # 10-16: 「查看」 a person / a thing / a place, as the player knows it (core/inspect)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.core import inspect as _inspect

            target = (parse_qs(urlparse(self.path).query).get("target") or [""])[0]
            self._send_json(_inspect.detail(rt.root, target, branch=rt._branch()))
            return True
        if route in _RUNREADS:  # read-only views of the run for the 1.0 UI (orchestration · contract · settlement)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            if route.endswith("/graph"):
                from neonrp.core import orchestration

                self._send_json({"graph": orchestration.graph(rt.root), "default": orchestration.default_graph(rt.root)})
            elif route.endswith("/entities"):  # also /debug/entities
                # 10-08: one class's instances with their props (the play layer draws the conditions on you — status —
                # with their turns left; schema's entries carry ids + names only)
                from neonrp.core.registry import load_registry

                q = parse_qs(urlparse(self.path).query)
                cls = (q.get("cls") or [""])[0]
                clue = (q.get("clue") or [""])[0] in ("1", "true")  # 10-15: only the clues (any class when cls is not given)
                reg = load_registry(rt.root)
                if cls not in reg.classes and not clue:
                    self._send_json({"cls": cls, "entities": []})
                else:
                    # 10-15: a person's persona / rules / goals / relationship truths are the host's — the play read gives
                    # the fields the screen may show (core/people.play_props); the debug read keeps everything
                    from neonrp.core import people as _people
                    from neonrp.core.output_lang import prompt_lang

                    from neonrp.core import play_view as _pv

                    debug = route.endswith("/debug/entities")
                    full = debug or cls == "player" or not (reg.is_person(cls) if cls else False)
                    vis = None if debug or cls == "player" else _pv.visible_entries(rt.root, reg)  # nothing the player has not come across
                    lang = prompt_lang(rt.root)
                    from neonrp.core import fallback_art as _fb

                    def stand_in(e: Any) -> dict[str, str]:  # no picture: which silhouette / icon (10-17, core/fallback_art)
                        if reg.is_person(e.cls):
                            return {"portrait_fallback": _fb.portrait(e.props or {})}
                        return {"icon_fallback": _fb.icon(e.props or {}, name=e.name)}

                    self._send_json({"cls": cls, "entities": [{"id": e.id, "name": e.name, "parent": e.parent,
                                                               "props": (e.props or {}) if full else _people.play_props(e.props or {}, root=rt.root, lang=lang),
                                                               **stand_in(e)}
                                                              for e in (reg.of_class(cls) if cls else list(reg.entries.values()))
                                                              if (vis is None or e.id in vis) and (not clue or reg.is_clue(e))]})
            elif route.endswith("/settlement/quiz"):  # 10-15 (PLATFORM-PLAY-RULES §5 §9): 真相三问, after the ending only
                from neonrp.core import truth_quiz

                self._send_json(truth_quiz.quiz(rt.root))
            elif route.endswith("/settlement/milestones"):
                from neonrp.core import milestones

                self._send_json(milestones.listing(rt.root))
            elif route.endswith("/achievements"):
                from neonrp.core import achievements

                self._send_json(achievements.listing(rt.root))
            elif route.endswith("/objective"):  # 10-15 (§5.18): the stage's goal, the commissions, how the run ends
                from neonrp.core import objective as _objective

                self._send_json(_objective.objective(rt.root))
            elif route.endswith("/engine/audio"):  # 10-15: music · ambient · mood now, and the credits (core/audio)
                from neonrp.core import audio as _audio

                self._send_json(_audio.current(rt.root))
            elif route.endswith("/people"):  # 10-15 (the standard front end §5.14)
                from neonrp.core import people as _people

                self._send_json(_people.people(rt.root))
            elif route.endswith("/beats"):
                # 10-07: every beat event the run produced so far (core/beat_events, the same derivation the turn
                # stream uses) — a front end catching up after a reconnect, the 1.0 UI's event log on open
                from neonrp.core import beat_events
                from neonrp.core.orchestration_trace import read_turn_traces

                q = parse_qs(urlparse(self.path).query)
                try:
                    since = max(0, int((q.get("since") or ["0"])[0]))
                except ValueError:
                    since = 0
                trs = read_turn_traces(rt.root, rt._branch())
                evs, _node = beat_events.from_traces(trs, root=rt.root)
                rows = [{"seq": i, **d, "kind": k} for i, (k, d) in enumerate(evs)][since:]  # the event name last: a payload never hides it
                self._send_json({"events": rows, "next": len(evs), "names": list(beat_events.EVENTS)})
            elif route.endswith("/sheet"):  # 10-14 (the standard front end §5.9)
                from neonrp.core import sheet as _sheet

                self._send_json(_sheet.sheet(rt.root))
            elif route.endswith("/actions"):  # 10-14 (§5.11): `/` `@` `#` completion + the quick bar
                from neonrp.core import play_menu

                self._send_json(play_menu.catalog(rt.root))
            elif route.endswith("/player-card"):
                from neonrp.template import builder as _builder

                self._send_json(_builder.run_card(rt.root) or {})
            elif route.endswith("/contract"):
                from neonrp.template import contract as _contract

                self._send_json(_contract.run_contract(rt.root) or {})
            else:
                from neonrp.core import settlement as _settlement

                self._send_json(_settlement.read(rt.root) or {})
            return True
        if route == _WDATA:
            if rt is None:
                self.send_error(409, "no play session")
                return True
            import json as _json

            from neonrp.core.paths import get_data_dir_name

            name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0]
            if name not in WORLD_DATA:
                self.send_error(404, "unknown world data")
                return True
            try:
                d = _json.loads((rt.root / get_data_dir_name(rt.root) / "world" / f"{name}.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                d = {}
            self._send_json(d if isinstance(d, dict) else {})
            return True
        if route == _VIEWS:
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.template import v3

            rec = TP_meta(rt.root)
            self._send_json({"views": v3.views_data(rt.root, rec.get("ui") if rec else None),
                             "panels": ((rec or {}).get("ui") or {}).get("panels") or []})
            return True
        if route == _PLAY:
            from neonrp import template as TP

            v = TP.run_view(rt.root) if rt is not None else None
            if v is None:
                self._send_json({"template": None})
            else:
                self._send_json(v)
            return True
        if route.startswith(_AUDIO):  # the platform pool (core/audio): no session needed
            from neonrp.core import audio as _audio

            f, fresh = _audio.pool_file(unquote(route[len(_AUDIO):]))
            self._send_media(f, immutable=fresh)
            return True
        if route != _LOCAL and not route.startswith(_LOCAL + "/"):
            return False
        if route.endswith("/export"):
            return False  # the package download lives with the other downloads (launcher_routes · template/package.py)
        from neonrp import template as TP

        found = TP.discover()
        if route == _LOCAL:
            rows = []
            cold = [d for d in found.values() if not lint_is_cached(d)]
            if cold:  # 引擎刚起:先回列表(不带 lint),后台把 lint 补进缓存 —— 页面不用等 6–9 秒;界面看到 checking 会再取
                _warm(cold)
            for tid, d in found.items():
                if d in cold:
                    try:
                        meta = TP.load(d).meta()
                    except TP.TemplateError:
                        continue
                    rows.append({**meta, "publishable": None, "counts": None, "checking": True})
                    continue
                r = lint_cached(d)
                rows.append({**r["meta"], "publishable": r["publishable"], "counts": r.get("counts")})
            self._send_json({"version": TEMPLATE_VERSION, "templates": rows})
            return True
        rest = route[len(_LOCAL) + 1:]
        tid, _, sub = rest.partition("/")
        tid = unquote(tid)
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        if sub == "lint":
            self._send_json(lint_cached(found[tid]))
        elif sub == "publish":  # the free-zone dry run: the checks + the author's work from this template (core/template_publish)
            from neonrp.core import template_publish as _tp

            lang = (parse_qs(urlparse(self.path).query).get("lang") or [""])[0] or None
            self._send_json(_tp.status(TP.load(found[tid]), lang=lang, lint=lint_cached(found[tid])))
        elif sub == "cover":
            t = TP.load(found[tid])
            p = (t.dir / str(t.card.get("cover") or "")).resolve()
            ok = bool(t.card.get("cover")) and p.is_file() and p.is_relative_to(t.dir.resolve())
            self._send_file(p if ok else None)
        elif sub == "contract":
            from neonrp.template import v3

            fmt = (parse_qs(urlparse(self.path).query).get("fmt") or [""])[0]
            t = TP.load(found[tid])
            with v3._scratch(t, None) as root:
                c = v3.contract(t, root)
            if fmt in ("ts", "gd"):
                body = (v3.gen_ts(c) if fmt == "ts" else v3.gen_gd(c)).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors_headers()
                self.end_headers()
                self.wfile.write(body)
            else:
                self._send_json(c)
        elif sub == "assets":
            t = TP.load(found[tid])
            slots = TP.asset_slots(t)
            # 角色名的四种写法(ios4 10-23:本地 Hub / iOS 的角色页在外语界面下也显示中文名)
            from neonrp.template import i18n as _i18n
            try:
                names = _i18n.soul_names(t, {s["slot"].split(":", 1)[1]: s.get("label") or "" for s in slots if s.get("cls") == "soul" and s.get("name") == "portrait"})
            except Exception:  # noqa: BLE001 — names are a nicety: the slots still go out
                names = {}
            self._send_json({"slots": slots, "names": names})
        elif sub == "assets/file":
            q = parse_qs(urlparse(self.path).query)
            slot, part = (q.get("slot") or [""])[0], (q.get("part") or ["image"])[0]  # part=video: a CG slot's video (10-14)
            # variant=<sid>: that companion's picture (10-15); none given → the bound run's companion, when it plays this template
            variant = (q.get("variant") or [""])[0] or None
            if variant is None and rt is not None and str((TP_meta(rt.root) or {}).get("id") or "") == tid:
                variant = TP.run_companion(rt.root)
            # a template picture changes only when its file does: browsers keep it a minute, then ask again with the ETag;
            # &w=<px> = a small copy for cards / avatars (core/thumbs, 10-15)
            from neonrp.core import thumbs

            p = TP.slot_file(TP.load(found[tid]), slot, part=part, variant=variant)
            if part != "video":
                p = thumbs.thumb(p, thumbs.width((q.get("w") or [""])[0]))
            self._send_file(p, cache="private, max-age=60, must-revalidate")
        elif sub == "audio":  # a template's own audio (core/audio: template.json / location.json / plot stage values)
            from neonrp.core import audio as _audio

            q = parse_qs(urlparse(self.path).query)
            rel, h = (q.get("path") or [""])[0], (q.get("h") or [""])[0]
            d = found[tid].resolve()
            f = (d / rel).resolve() if rel.startswith("assets/") else None
            ok = f is not None and f.is_file() and f.is_relative_to(d) and f.suffix.lower() in _audio.AUDIO_EXTS
            self._send_media(f if ok else None, immutable=bool(ok and h and h == _audio.file_hash(f)))
        elif sub == "ui":
            self._send_json(_ui_view(TP.load(found[tid])))
        elif sub == "plots":
            self._send_json(_plots_view(TP.load(found[tid])))
        elif sub == "builder":  # the player builder screen (template/builder.py, 10-14)
            from neonrp.template import builder as _builder

            self._send_json(_builder.view(TP.load(found[tid])))
        elif sub == "builder/image":
            from neonrp.template import builder as _builder

            q = parse_qs(urlparse(self.path).query)
            one = lambda k: (q.get(k) or [""])[0]  # noqa: E731
            t = TP.load(found[tid])
            self._send_file(_builder.companion_image(t, one("sid")) if one("sid") else _builder.option_image(t, one("field"), one("option")))
        elif sub == "creation":  # the limited creation desk's form (template/creation.py, 10-13)
            from neonrp.template import creation

            self._send_json(creation.form(TP.load(found[tid])))
        elif sub == "creation/orchestration":  # each preset's read-only graph for the desk (core/orch_presets, 10-18)
            from neonrp.core import orch_presets

            self._send_json(orch_presets.views(TP.load(found[tid])))
        elif sub == "":
            self._send_json(TP.load(found[tid]).meta())
        else:
            self.send_error(404)
        return True

    def _template_route_post(self, rt: Any) -> bool:
        route = urlparse(self.path).path.rstrip("/")
        if route in ("/api/v1/report/ai", "/api/v1/report/ai/done"):  # 10-21 (App Store 1.2): report AI content (core/ai_report)
            from neonrp.core import ai_report

            body = self._read_json_body() or {}
            if route.endswith("/done"):
                self._send_json({"ok": ai_report.done(str(body.get("id") or ""))})
                return True
            from neonrp.core.output_lang import prompt_lang

            lang = str(body.get("lang") or (prompt_lang(rt.root) if rt is not None else "zh"))
            try:
                self._send_json(ai_report.submit(body, root=rt.root if rt is not None else None, lang=lang))
            except ValueError as e:
                code = str(e)
                self._send_json({"ok": False, "error": code, "message": str(ai_report._T(lang if lang in ("zh", "en", "ja", "ko") else "zh").get(code) or code)}, status=400)
            return True
        if route in ("/api/v1/play/engine/settlement/quiz", "/api/v1/play/engine/settlement/leave"):  # 10-15 settlement
            if rt is None:
                self.send_error(409, "no play session")
                return True
            if not rt._busy.acquire(blocking=False):
                self._send_json({"error": "a turn is in progress"}, status=409)
                return True
            try:
                if route.endswith("/quiz"):
                    from neonrp.core import truth_quiz

                    body = self._read_json_body() or {}
                    ans = body.get("answers") if isinstance(body.get("answers"), list) else []
                    out = truth_quiz.answer(rt.root, ans, str(body.get("take") or "") or None)
                    self._send_json(out, status=409 if out.get("error") == "locked" else 200)
                else:
                    from neonrp.core import milestones

                    self._send_json(milestones.leave(rt.root))
            finally:
                rt._busy.release()
            return True
        if route == _INSPECT:  # 10-16: the detail, with a thing's description written when the world has none (core/inspect)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            from neonrp.core import inspect as _inspect

            target = str((self._read_json_body() or {}).get("target") or "")
            if not rt._busy.acquire(blocking=False):  # a turn is writing the run: answer what is there, write nothing
                self._send_json({**_inspect.detail(rt.root, target, branch=rt._branch()), "busy": True})
                return True
            try:
                self._send_json(_inspect.describe(rt.root, target, branch=rt._branch()))
            finally:
                rt._busy.release()
            return True
        if route == "/api/v1/play/engine/choices":  # 10-15: a few more options for this moment — read-only (core/more_choices)
            if rt is None:
                self.send_error(409, "no play session")
                return True
            if not rt._busy.acquire(blocking=False):  # a turn is running: the moment is not settled yet
                self._send_json({"error": "a turn is in progress"}, status=409)
                return True
            try:
                from neonrp.core.more_choices import more_choices

                body = self._read_json_body() or {}
                avoid = body.get("avoid") if isinstance(body.get("avoid"), list) else []
                try:
                    n = int(body.get("n") or 3)
                except (TypeError, ValueError):
                    n = 3
                self._send_json(more_choices(rt.root, n=n, avoid=[str(a) for a in avoid], branch=rt._branch()))
            finally:
                rt._busy.release()
            return True
        if route.startswith(_LOCAL + "/") and route.endswith("/publish"):  # 10-16: to the Hub's free zone with the author's account
            from neonrp import template as TP
            from neonrp.core import template_publish as _tp

            tid = unquote(route[len(_LOCAL) + 1:-len("/publish")])
            found = TP.discover()
            if tid not in found:
                self.send_error(404, "no such template")
                return True
            body = self._read_json_body() or {}
            lang = str(body.get("lang") or "") or None
            zone = "curated" if body.get("zone") == "curated" else "open"   # curated = the web Hub desk (the default zone's review)
            try:
                if body.get("official") is True:
                    self._send_json(_tp.publish_official(TP.load(found[tid]), lang=lang, lint=lint_cached(found[tid])))
                else:
                    self._send_json(_tp.publish(TP.load(found[tid]), lang=lang, lint=lint_cached(found[tid]), zone=zone))
            except _tp.PublishError as e:
                self._send_json(e.to_dict(), status=e.status)
            return True
        if route.startswith(_LOCAL + "/") and route.endswith(("/assets/upload", "/assets/generate")):
            return self._template_asset_post(route)
        if route.startswith(_LOCAL + "/") and route.endswith(("/fork", "/ops")):
            return self._template_author_post(route, rt)
        if route.startswith(_LOCAL + "/") and route.endswith("/plots"):
            return self._template_plot_post(route)
        if route.startswith(_LOCAL + "/") and route.endswith("/builder/generate"):
            from neonrp import template as TP
            from neonrp.template import builder as _builder

            tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
            found = TP.discover()
            if tid not in found:
                self.send_error(404, "no such template")
                return True
            body = self._read_json_body() or {}
            try:
                self._send_json(_builder.generate(TP.load(found[tid]), str(body.get("field") or ""), body, lang=str(body.get("lang") or "zh")))
            except _builder.BuilderError as e:
                self._send_json({"ok": False, "errors": e.errors}, status=400)
            return True
        if route.startswith(_LOCAL + "/") and route.endswith("/builder/check"):
            from neonrp import template as TP
            from neonrp.template import builder as _builder

            tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
            found = TP.discover()
            if tid not in found:
                self.send_error(404, "no such template")
                return True
            errs, _norm = _builder.check(TP.load(found[tid]), self._read_json_body() or {})
            self._send_json({"ok": not errs, "errors": errs})
            return True
        if route.startswith(_LOCAL + "/") and route.endswith("/creation/truth-quiz/generate"):
            return self._template_creation_quiz(route)
        if route.startswith(_LOCAL + "/") and route.endswith("/creation/work"):
            return self._template_creation_work(route)
        if route.startswith(_LOCAL + "/") and route.endswith("/creation/assist"):  # say it in one sentence (creation_assist_routes)
            from neonrp.webui import creation_assist_routes
            return creation_assist_routes.post(self, route)
        if route.startswith(_LOCAL + "/") and route.endswith(("/creation/check", "/creation")):
            return self._template_creation_post(route)
        if route.startswith(_LOCAL + "/") and route.endswith("/graph-lint"):
            # 10-07: warnings for the orchestration editor's draft graph (read-only: lint in a throwaway run)
            from neonrp.template import v3

            tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
            g = (self._read_json_body() or {}).get("graph")
            if not isinstance(g, dict):
                self._send_json({"ok": False, "error": "graph 要是一个对象"}, status=400)
                return True
            try:
                self._send_json({"ok": True, "lint": v3.lint_graph_of(tid, g)})
            except KeyError:
                self.send_error(404, "no such template")
            return True
        if route.startswith(_LOCAL + "/") and route.endswith("/graph-test"):
            # 10-17: the orchestration editor's chat test runs the real engine on a stub model (was a page-side mock)
            from neonrp import template as TP
            from neonrp.core import graph_test

            tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
            body = self._read_json_body() or {}
            lines = [str(x)[:400] for x in body.get("lines") or [] if str(x).strip()][:12]
            g = body.get("graph")
            if not lines or (g is not None and not isinstance(g, dict)):
                self._send_json({"ok": False, "error": "lines 要是一句以上;graph 要是一个对象"}, status=400)
                return True
            if tid not in TP.discover():
                self.send_error(404, "no such template")
                return True
            if str(body.get("model") or "") == "real":   # ④ niko 10-17: the player's own model, clearly a paid run
                return self._graph_test_real(rt, tid, lines, g, str(body.get("session") or ""))
            try:
                # the host keeps a plan board (a line the player said), so the commit word has something to settle (plan_loop)
                res = graph_test.run_isolated({"template": tid, "lines": lines, **({"graph": g} if g else {}),
                                               "defaults": {"host": graph_test.EDITOR_HOST}})
            except Exception as exc:  # noqa: BLE001 — the editor shows why (a timeout, a broken draft)
                self._send_json({"ok": False, "error": str(exc)[:300]}, status=502)
                return True
            self._send_json({"ok": True, **res})
            return True
        if route != _TICK:
            return False
        if rt is None:
            self.send_error(409, "no play session")
            return True
        body = self._read_json_body() or {}
        try:
            turns = max(1, min(MAX_TICKS, int(body.get("turns") or 1)))
        except (TypeError, ValueError):
            turns = 1
        if not rt._busy.acquire(blocking=False):
            self._send_json({"ok": False, "error": "a turn is in progress"}, status=409)
            return True
        try:
            from neonrp.core import sdk

            res = sdk.tick(rt.root, turns=turns)
        finally:
            rt._busy.release()
        self._send_json({"ok": True, "turns": [{"turn": r.turn, "applied": [a for a in r.applied if a.get("op") not in ("add", "set")],
                                                "changed": sum(1 for a in r.applied if a.get("op") in ("add", "set")),
                                                "created": r.created, "ended": r.ended, "triggered": [t.get("id") for t in r.triggered]}
                                               for r in res]})
        return True

    def _graph_test_real(self, rt: Any, tid: str, lines: list[str], g: Any, sid: str) -> bool:
        """The orchestration editor's chat test on the player's own model (④ niko 10-17): a throwaway run kept per
        chat (``session``), so each new line plays one more turn instead of replaying the whole chat on a paid model;
        a changed draft or template starts the run over. Errors come back as {error: code, message: 人话}."""
        import hashlib
        import json as _json
        import re as _re
        import shutil
        import tempfile

        from neonrp.core import graph_test

        conf = None
        try:   # the model this engine's run plays on; without a run, the one the player picked in settings
            p = Path(rt.root) / ".neonrp" / "config.json" if rt is not None else None
            if p is not None and p.is_file():
                c = _json.loads(p.read_text(encoding="utf-8"))
                if str(((c or {}).get("llm") or {}).get("provider") or "") not in ("", "stub"):
                    conf = c
            if conf is None:
                from neonrp.commands.web import _resolve_creation_preset
                from neonrp.presets import build_config_dict

                pid = _resolve_creation_preset("")
                conf = build_config_dict(pid) if pid else None
        except Exception:  # noqa: BLE001
            conf = None
        if not conf:
            self._send_json({"ok": False, "error": "no_model", "message": "还没选模型:到设置里选一个模型再测"}, status=409)
            return True
        sid = _re.sub(r"[^A-Za-z0-9_-]", "", sid)[:40] or "default"
        gsig = hashlib.sha1(_json.dumps(g or {}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        hit = _REAL_TESTS.get(sid)
        if hit and hit["tpl"] == tid and hit["gsig"] == gsig and hit["n"] == len(lines) - 1 and Path(hit["dir"]).is_dir():
            todo = lines[-1:]   # go on from the kept run: one more turn
        else:
            if hit:
                shutil.rmtree(hit["dir"], ignore_errors=True)
            hit = {"tpl": tid, "gsig": gsig, "n": 0, "dir": tempfile.mkdtemp(prefix="wl-graph-real-")}
            todo = lines
        _REAL_TESTS[sid] = hit
        for old in list(_REAL_TESTS)[:-6]:   # a few chats at most
            shutil.rmtree(_REAL_TESTS.pop(old)["dir"], ignore_errors=True)
        try:
            res = graph_test.run_isolated({"template": tid, "lines": todo, "model": "real", "config": conf,
                                           "root": str(Path(hit["dir"]) / "run"), **({"graph": g} if g else {})},
                                          timeout=min(900.0, 240.0 * len(todo)))
        except Exception as exc:  # noqa: BLE001 — the run is in an unknown state: the next line starts over
            _REAL_TESTS.pop(sid, None)
            shutil.rmtree(hit["dir"], ignore_errors=True)
            self._send_json({"ok": False, "error": _real_error_code(str(exc)), "message": str(exc)[:300]}, status=502)
            return True
        hit["n"] = len(lines)
        self._send_json({"ok": True, "session": sid, "ran": len(todo), **res})
        return True

    def _template_creation_post(self, route: str) -> bool:
        """The limited creation desk: ``…/creation/check`` validates a submission; ``…/creation`` also writes it as one
        plot of a template the creator owns (a fork) and re-lints. The template's own files are never edited."""
        from neonrp import template as TP
        from neonrp.template import author, creation

        tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
        found = TP.discover()
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        t = TP.load(found[tid])
        body = self._read_json_body() or {}
        add = body.get("addition")
        if not isinstance(add, dict):
            self._send_json({"ok": False, "error": "addition 要是一个对象"}, status=400)
            return True
        probs = creation.check(t, add)
        if route.endswith("/check") or probs:
            self._send_json({"ok": not probs, "problems": probs}, status=200 if route.endswith("/check") or not probs else 400)
            return True
        if not author.writable(t):
            self._send_json({"ok": False, "error": f"模板 {t.id} 是内置的(只读)——先另存一份再创作"}, status=403)
            return True
        pid = str(body.get("id") or "").strip() or f"C{len(t.plots) + 1:02d}"
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", pid):
            self._send_json({"ok": False, "error": "id 只能用字母、数字、- 和 _"}, status=400)
            return True
        rel = f"plots/{pid}"
        target = t.dir / rel / "plot.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(creation.to_plot(add, pid), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if rel not in t.plots:
            d = json.loads((t.dir / "template.json").read_text(encoding="utf-8"))
            d["plots"] = [*(d.get("plots") or []), rel]
            (t.dir / "template.json").write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        self._send_json({"ok": True, "plot": rel, "lint": TP.lint(found[tid])})
        return True

    def _template_creation_quiz(self, route: str) -> bool:
        """The creation desk's 「点生成」 for the 「真相三问」 (PLATFORM-PLAY-RULES §11): ``POST …/<template>/creation/
        truth-quiz/generate {reveal?, story?, lang?}`` → {ok, questions, reward_soul?, problems} — a draft the creator edits
        (template/creation_quiz.generate); {ok: false, error: closed 400 | no_truth 422 | model 502}."""
        from neonrp import template as TP
        from neonrp.template import creation_quiz

        tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
        found = TP.discover()
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        body = self._read_json_body() or {}
        res = creation_quiz.generate(TP.load(found[tid]), reveal=body.get("reveal"), story=str(body.get("story") or ""),
                                     lang=str(body.get("lang") or ""))
        self._send_json(res, status=200 if res.get("ok") else {"closed": 400, "no_truth": 422}.get(str(res.get("error")), 502))
        return True

    def _template_creation_work(self, route: str) -> bool:
        """The creation desk's 「存」 (web Hub · local Hub): ``POST …/<template>/creation/work {addition, card?, id?}`` →
        the creator's work (a copy of the template, made on the first save) with the addition as its one plot and the
        card they wrote → {ok, id, plot, slots, lint}; 400 {problems} when the form does not pass."""
        from neonrp import template as TP
        from neonrp.template import author, creation

        tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
        found = TP.discover()
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        t = TP.load(found[tid])
        body = self._read_json_body() or {}
        add, card = body.get("addition"), body.get("card")
        if not isinstance(add, dict) or (card is not None and not isinstance(card, dict)):
            self._send_json({"ok": False, "error": "addition (and card) must be objects"}, status=400)
            return True
        probs = creation.check(t, add)
        if probs:
            self._send_json({"ok": False, "problems": probs}, status=400)
            return True
        wid = str(body.get("id") or "").strip() or f"{t.id[:43]}-mine"
        if not author.ID_RE.match(wid):
            self._send_json({"ok": False, "error": "id: 2–48 chars, lowercase letters / digits / '-'"}, status=400)
            return True
        try:
            w = creation.save(t, add, work_id=wid, card=card)
        except TP.TemplateError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=409 if "not a work made from" in str(exc) else 400)
            return True
        except OSError as exc:  # read-only store / disk
            self._send_json({"ok": False, "error": str(exc)[:300]}, status=502)
            return True
        self._send_json({"ok": True, "id": w.id, "plot": f"plots/{creation.WORK_PLOT}", "slots": creation.slots(w),
                         "orchestration": _orch_of(w)})
        # no lint here (a full lint is seconds natively, a minute in the browser engine): the desk's pre-publish check
        # (GET …/<work>/publish) lints right after, cached, without holding up 「存」
        return True

    def _template_plot_post(self, route: str) -> bool:
        """Write one plots/<id>/plot.json of a template the creator owns (forked into the write store), then re-lint."""
        from neonrp import template as TP
        from neonrp.template import author

        tid = unquote(route[len(_LOCAL) + 1:].partition("/")[0])
        found = TP.discover()
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        t = TP.load(found[tid])
        if not author.writable(t):
            self._send_json({"ok": False, "error": f"模板 {t.id} 是内置的(只读)——先另存一份再改"}, status=403)
            return True
        body = self._read_json_body() or {}
        rel, data = str(body.get("path") or ""), body.get("data")
        if not _PLOT_PATH.fullmatch(rel):
            self._send_json({"ok": False, "error": "path 只能是 plots/<id>/plot.json"}, status=400)
            return True
        if not isinstance(data, dict):
            self._send_json({"ok": False, "error": "data 要是一个 JSON 对象"}, status=400)
            return True
        target = t.dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(target)
        self._send_json({"ok": True, "path": rel, "lint": TP.lint(found[tid])})
        return True

    def _template_asset_post(self, route: str) -> bool:
        from neonrp import template as TP

        rest = route[len(_LOCAL) + 1:]
        tid, _, sub = rest.partition("/")
        found = TP.discover()
        tid = unquote(tid)
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        t = TP.load(found[tid])
        try:
            if sub == "assets/upload":
                q = parse_qs(urlparse(self.path).query)
                slot, ext = (q.get("slot") or [""])[0], (q.get("ext") or [".png"])[0]
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > TP.MAX_UPLOAD:
                    self._send_json({"ok": False, "error": "image is empty or larger than 8 MB"}, status=413)
                    return True
                row = TP.put_asset(t, slot, self.rfile.read(n), ext=ext)
                _mirror(t, slot, None, "upload")
            else:
                body = self._read_json_body() or {}
                slot, prompt = str(body.get("slot") or ""), str(body.get("prompt") or "") or None
                row = TP.generate_asset(t, slot, prompt=prompt)
                _mirror(t, slot, prompt or row.get("prompt"), "generate")
        except TP.TemplateError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return True
        except (RuntimeError, OSError) as exc:  # no image backend / backend down / read-only store
            self._send_json({"ok": False, "error": str(exc)[:300]}, status=502)
            return True
        self._send_json({"ok": True, "slot": row})
        return True

    def _template_author_post(self, route: str, rt: Any) -> bool:
        from neonrp import template as TP
        from neonrp.template import author

        rest = route[len(_LOCAL) + 1:]
        tid, _, sub = rest.partition("/")
        tid = unquote(tid)
        found = TP.discover()
        if tid not in found:
            self.send_error(404, "no such template")
            return True
        body = self._read_json_body() or {}
        try:
            if sub == "fork":
                if not TP.can_fork(TP.load(found[tid])):   # 10-17: of the official worlds only the forkable ones offer a copy
                    from neonrp.core import template_publish as _tp

                    msg = _tp._msg("not_forkable", str(body.get("lang") or "") or None)
                    self._send_json({"ok": False, "error": "not_forkable", "message": msg}, status=403)
                    return True
                t2 = author.fork(found[tid], str(body.get("id") or ""), title=str(body.get("title") or "") or None)
                self._send_json({"ok": True, "template": t2.meta(), "workshop": bool(author.workshop(t2.id))})
                return True
            res = author.apply_ops(found[tid], body.get("ops"))
        except TP.TemplateError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
            return True
        except OSError as exc:  # read-only store / disk
            self._send_json({"ok": False, "error": str(exc)[:300]}, status=502)
            return True
        if res.get("ok") and rt is not None:
            _sync_run_ui(rt.root, tid, res.get("ui"))
        self._send_json(res, status=200 if res.get("ok") else 422)
        return True


_REAL_TESTS: dict[str, dict[str, Any]] = {}   # the editor's real-model chats: session → {tpl, gsig, n lines played, dir}


def _drop_real_tests() -> None:
    import shutil

    for v in list(_REAL_TESTS.values()):
        shutil.rmtree(v["dir"], ignore_errors=True)


__import__("atexit").register(_drop_real_tests)


def _real_error_code(msg: str) -> str:
    """A provider failure as a code the editor turns into 人话: no_model · auth · credits · timeout · model."""
    m = msg.lower()
    if "no model configured" in m:
        return "no_model"
    if any(k in m for k in ("401", "unauthorized", "invalid api key", "invalid_api_key", "authentication")):
        return "auth"
    if any(k in m for k in ("402", "insufficient", "quota", "balance", "credit")):
        return "credits"
    if "timeout" in m or "timed out" in m:
        return "timeout"
    return "model"


_PLOT_PATH = re.compile(r"plots/[A-Za-z0-9_-]{1,40}/plot\.json")
_LINT_CACHE: dict[str, tuple[Any, dict]] = {}


def _tree_sig(*dirs: Any) -> tuple:
    """(path, mtime_ns, size) of every file under ``dirs`` — changes whenever anything in them is edited / added / removed."""
    from pathlib import Path

    out = []
    for d in dirs:
        if d is None:
            continue
        d = Path(d)
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                st = f.stat()
                out.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(sorted(out))


def lint_is_cached(d: Any) -> bool:
    from neonrp import template as TP

    hit = _LINT_CACHE.get(str(d))
    if not hit:
        return False
    try:
        return hit[0] == _tree_sig(d, TP.world_dir(TP.load(d)))
    except Exception:  # noqa: BLE001
        return False


_WARMING: set[str] = set()


def _warm(dirs: list) -> None:
    import threading

    todo = [d for d in dirs if str(d) not in _WARMING]
    if not todo:
        return
    _WARMING.update(str(d) for d in todo)

    def run() -> None:
        for d in todo:
            try:
                lint_cached(d)
            except Exception:  # noqa: BLE001 — a broken template: its own /lint call reports it
                pass
            finally:
                _WARMING.discard(str(d))

    threading.Thread(target=run, daemon=True, name="template-lint-warm").start()


def lint_cached(d: Any) -> dict:
    """``template.lint`` with a cache keyed by the template folder (+ the built-in world it uses): the list of templates is
    the first thing every page asks for, and linting five templates took 6–9 s on every load (「引擎没打开」)."""
    from neonrp import template as TP

    try:
        wd = TP.world_dir(TP.load(d))
    except Exception:  # noqa: BLE001 — a template that does not load: lint says why, uncached
        return TP.lint(d)
    key, sig = str(d), _tree_sig(d, wd)
    hit = _LINT_CACHE.get(key)
    if hit and hit[0] == sig:
        return hit[1]
    r = TP.lint(d)
    _LINT_CACHE[key] = (sig, r)
    return r


def _plots_view(t: Any) -> dict:
    """Every plot of a template, parsed, with the files beside it (ending CG etc.). Read-only view for the plot graph."""
    from neonrp.template import author, can_fork

    rows = []
    for f in sorted((t.dir / "plots").glob("*/plot.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            rows.append({"path": f"plots/{f.parent.name}/plot.json", "error": str(exc)[:200]})
            continue
        rows.append({"path": f"plots/{f.parent.name}/plot.json", "data": data, "files": sorted(p.name for p in f.parent.iterdir() if p.is_file())})
    return {"id": t.id, "writable": author.writable(t), "forkable": can_fork(t), "plots": rows}


def _ui_view(t: Any) -> dict[str, Any]:
    """What the 3.0 studio's 组装 · Lint tab edits: the merged ui (pack < mixins < template), the mixin set, world data."""
    import json as _json

    from neonrp.template import author, can_fork, v3

    wd: dict[str, Any] = {}
    try:
        with v3._scratch(t, None) as root:
            from neonrp.core.paths import get_data_dir_name

            for name in WORLD_DATA:
                p = root / get_data_dir_name(root) / "world" / f"{name}.json"
                wd[name] = _json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
            u = v3.ui(t)
    except Exception:  # noqa: BLE001 — a template that does not build: lint says why
        u = {"slots": [], "views": [], "panels": [], "prompts": {}, "recipe": {}, "budget": 20000}
    return {"id": t.id, "ui": u, "writable": author.writable(t), "forkable": can_fork(t), "pack": t.pack_name, "mixins": [str(m) for m in t.pack.get("mixins") or []],
            "mixins_available": author.mixins_available(), "world_data": wd, "forked_from": t.data.get("forked_from")}


def _sync_run_ui(root: Any, tid: str, u: Any) -> None:
    """The bound run is of this template → its presentation record follows the edit (views / slots / prompts show at once;
    rules — mixins, classes, world data — take effect in a new run)."""
    import json as _json

    from neonrp.core.paths import get_data_dir_name

    p = root / get_data_dir_name(root) / "meta" / "template.json"
    try:
        rec = _json.loads(p.read_text(encoding="utf-8"))
        if isinstance(rec, dict) and rec.get("id") == tid and isinstance(u, dict):
            rec["ui"] = u
            p.write_text(_json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, ValueError):
        pass


def _mirror(t: Any, slot: str, prompt: str | None, backend: str) -> None:
    from neonrp import template as TP
    from neonrp.template import author

    try:
        author.mirror(TP.load(t.dir), slot, TP.slot_file(TP.load(t.dir), slot), prompt=prompt, backend=backend)
    except Exception:  # noqa: BLE001 — the workshop copy never fails the upload
        pass


def TP_meta(root: Any) -> dict[str, Any] | None:  # noqa: N802 — the run's template record (game/meta/template.json)
    import json

    from neonrp.core.paths import get_data_dir_name

    try:
        d = json.loads((root / get_data_dir_name(root) / "meta" / "template.json").read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None

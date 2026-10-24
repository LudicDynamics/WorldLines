# Template authoring ops

`POST /api/v1/local/templates/<id>/ops {ops: [...]}` — every op is verified first; one refusal and nothing is written; the template is re-linted afterwards. CLI: `neonrp template --help`.

```
Authoring a template (Template v3 · the 3.0 studio's 组装 · Lint): fork one, apply creator ops to it, mirror assets.

A template is edited only where it is writable: under ``NEONRP_TEMPLATE_WRITE_DIR`` (WorldLines' own template store).
Built-in / example templates are read-only — fork first. Every edit goes through ``apply_ops``: all ops are verified
before anything is written (one refused → nothing lands), then the template is re-linted.

A template can also start from nothing (``blank``): the engine's blank world as its own ``world/``, no characters.

Ops (the mock's creator ops, now against the template on disk):

    edit_card     {title?, pitch?, tags?, lang?}
    set_mode      {ending?, freedom?}
    set_mixins    {mixins: [...]}                    pack mixins (economy / factions …)
    add_slot      {cls, slot, kind?, required?, recipe?, ratio?, scope?, fallback?}
    remove_slot   {cls, slot}
    edit_prompt   {id, text}                         named prompt (ui.prompts); text null removes it
    edit_recipe   {key: backend|style, value}
    set_view      {view: {id, title, bind, widget, actions?, layout?}}
    remove_view   {id}
    set_budget    {value}
    register_class{name, policy?}                    a template-level class (world-overlay game/meta/classes.json)
    set_policy    {cls, policy}                      growth policy of a class (same overlay)
    set_world_data{name: economy|factions, data}     mixin world data (world-overlay game/world/<name>.json)
    set_orchestration{graph}                         the template's graph, stored as a patch on the pack default (orchestration.json);
                                                     nodes.resolve.state = pseudo | jev: how the Resolve beat writes state
    set_play_contract{contract}                      "<id>@<version>" of a play contract; "" drops it
    set_soul_orchestration{sid, graph}               one character's own graph in this world (core/soul_orchestration), stored as a
                                                     patch on what it gets without one: prompts/souls/<sid>/orchestration.json
    set_engine_setting{key, value}                   one whitelisted engine setting in the template's pack.engine (merged into the
                                                     run's game/meta/engine.json at build): turn.parallel.souls.per_soul.<sid>
                                                     (a character of this template; null = follow default_variant) ·
                                                     turn.parallel.souls.default_variant — values: legacy · S-judge · S-direct · S-free
    set_soul_ambient{sid, world}                     one character's simple world view in this world (core/soul_ambient):
                                                     prompts/souls/<sid>/ambient/world.json
    set_cast      {souls: [...]}                     who plays: {sid} world-native · {lib} a link into the character
                                                     library (copied in only when a run is built) · {path} · {pool, pick};
                                                     role npc / companion / player
    link_soul     {lib, role?}                       add one library character to the cast (set_cast with one more {lib} row;
                                                     an implicit all-native cast is written out first)

The asset workshop: when ``WORLDLINES_ASSETS_DIR`` is set, every image that lands in a slot is also copied to
``$WORLDLINES_ASSETS_DIR/worlds/<template id>/<cls>/<slot>/<inst>.<ext>`` (the production workshop; generated
prompts are appended to ``prompts.md`` there) — the template keeps the final, the workshop keeps the history.
```

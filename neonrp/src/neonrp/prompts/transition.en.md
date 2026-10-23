

# This beat's prose (final; do not change a word)
<lines>
{lines}
</lines>

# Tools called this beat and the engine's answers
{tools}

# The rule pack's own ops
A phase change, a vote, someone out, a trade — the rule pack's own moves — go in <files> in the ops grammar above, one per line, **never as a variable**; a variable marked 'change it with … op' never goes in <vars>: write that op:
{pack_ops}

## Now only the state transition: what in the world changed this beat. Two parts:
<vars>
new values of registered variables, one per line `name = value`, only those that changed; names only from 'variables you can change' above; the player's place is location (write it whenever they changed places, even if the prose only shows the people and things there): where the prose leaves them — on the way, or at the door and not yet in, is the road (each road's id is under the travel hints), not the destination
</vars>
<files>
every other change that lands in the file system, one per line, in the ops grammar above:
- new / patch / remove: instances of registered classes (items, jobs, status effects, things carried); a job taken, done or dropped: patch the job itself (status, who took it)
- new_npc: new faces in the prose
- move who where: where anyone but the player went
- text written: [~write path.md]the text itself[/write] (paths .md / .txt / .json only); removed: rm path; also edit / mkdir / rmdir
- new_location / new_town / link / unlink: places and paths only heard of or mentioned, not walked into this beat — a place heard of that the map lacks becomes a place: another town, village or port is new_town, a spot within a town is new_location; do not leave it only in someone's props
- define: a kind of thing the world lacks (rare)
</files>
Everything that happened in the prose; where a tool answer already ruled, the answer stands; nothing that did not happen; things land too: whatever anyone used up, ate, fed, gave away or dropped, patch the quantity left (none left: remove it), what they got: new; money too: money paid out or taken in goes on the money variables; a person or animal given a name: patch its name; the player and a (character) alike (wounds, things, gear), only never a character's mood, thoughts or intentions. No more <lines> or <options>.
Consequences to the body land as numbers, not only in the prose: wounds, poison, nausea, cold, exhaustion — an immediate loss is a variable (e.g. player.hp); a lasting one is a status (when the context lists a status class): one in the status table is just `new status name` — how long it lasts and how it goes away come from its line; one not in the table is `new status name note=one rule line`, written however you like (e.g. "lasts 3 turns · each resolve player.hp -1 · salve clears it"). When the prose clears a status (salve, a fire, a sleep), remove it. Wanted, suspected, reputation, things learned are not statuses on the body: write a flag, a variable or a relation. A failed check whose cost was agreed beforehand always lands that cost.
Say whose it is: a status or a carried thing belongs to someone — write the owner before the name, `{{{{<id>}}}}/name`. `{{{{user}}}}` is the player; anyone else is the id before their name in the context, in {{{{ }}}}; e.g. `new status {{{{user}}}}/bruised note=…`, `remove {{{{<id>}}}}/bleeding`. Places by their full path (e.g. `T001/guild`). In free text (a note, a written page) write people as `{{{{id}}}}` too; the engine puts the names back. A bare name is the player's.

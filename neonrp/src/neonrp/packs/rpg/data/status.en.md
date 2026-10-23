# Status table (rpg default). One per line: name: rule. Write it however you like; the engine reads only "lasts N turns / N hours" and "each resolve var ±n", the rest is for the narrator and the host.
# A world overrides or adds in game/rules/status.md; the world's line wins for the same name.
Light wound: lasts 3 turns · check -1, only for actions using the hurt part · flesh wound, pulls when moving · gone the resolve after it is bandaged
Grave wound: lasts 24 hours · check -3 on all physical actions · each resolve player.hp -1 (while unbandaged) · bandaging stops the bleeding; needs a healer or a day's rest
Sprain: lasts 3 turns · check -2, only DEX/STR · walking hurts, every step tested first · salve or a night's rest clears it
Bleeding: lasts 2 turns · each resolve player.hp -1 · the wound keeps seeping · a bandage or a staunching herb stops it at once
Poisoned: lasts 3 turns · each resolve player.hp -1 · stomach churning, cold sweat · an antidote or throwing it all up clears it
Nauseous: lasts 2 turns · check -1 on actions needing focus · stomach heaving · vomiting or something hot to drink eases it
Exhausted: lasts 8 hours · check -1 on all actions · heavy legs, slow reactions · a sleep clears it
Chilled: lasts 2 turns · check -1 · each resolve player.hp -1 · stiff hands and feet · a fire indoors or dry clothes clears it
Hungry: check -1 on physical actions · until a proper meal
Shaken: lasts 2 turns · check -2, only INT/CHA · racing heart, blank mind · someone calming you or leaving the danger clears it
Drunk: lasts 6 hours · check -2, only DEX/INT · loose-tongued (CHA talk not reduced) · sleep or a sobering broth clears it
Down: cannot act · rolls a check each resolve (SRD: d20 ≥ 10 is a success, 1 counts two failures, 20 gets up; three successes stabilize, three failures die) · first aid or healing that brings hp above 0 gets them up
Stabilized: still down and cannot act, but no longer rolls · healing or rest bringing hp above 0 gets them up
Dead: is dead · no longer acts or speaks

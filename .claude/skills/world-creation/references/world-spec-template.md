# World spec — fill-in form

A world spec is the author's description of one world. The agent turns it into a template folder.
Write the content in the world's own language. Keep ids ASCII. Leave a line empty when you have no answer;
the agent picks a default and says which.

```markdown
# <title>

id: <ascii-id>                      # becomes <id>.template
lang: zh | en | ja | ko
pack: rpg | pct | werewolf | monopoly          # rules: rpg = d20 open world, pct = percentile investigation
contract: open-adventure@1 | mystery-trpg@1 | murder-mystery@1 | romance-companion@1
ending: open | single | multi
freedom: free | semi | guided
pitch: <one line for the card>
tags: <3–5 words>

## Premise
<3–8 sentences: where, when, what is wrong, what the player can do about it>

## Places
<one town per block; town id T001, T002 …; one line per place>
T001 <town name> — <one-line overview>
- <place-id> · <name> · gate | street | facility | dock | road | … · connects: <place-id>, … · <one-line summary>

## People
<characters who think for themselves (souls): one block each>
### <sid> · <name>
- where: <place-id>
- looks / voice: <a concrete picture and how they talk>
- wants: <1–3 goals>
- will / won't: <what they agree to, refuse, bargain over>

<background people the narrator plays (no own mind): one line each>
- <npc-id> · <name> · <role> · at <place-id>

## Opening
<the first scene, 2–6 sentences, second person>
- <choice 1>
- <choice 2>

## Plot and endings
stages: <stage 1> → <stage 2> → …
- <ending-id> · true | alt | fail · <title> · reached when: <condition in words>

## World data
<facts the host must read: prices, distances, schedules, statuses, rules of this world>

## Art (optional)
style: <one line for every image>
cover: <what the cover shows>
```

Contract quick guide (`neonrp template contracts` prints the full list):

| contract | exit | endings | cast |
|---|---|---|---|
| `open-adventure@1` | a day or a segment | 0 or more | open |
| `mystery-trpg@1` | an ending | 3 or more, one `true` | fixed; truth quiz required |
| `murder-mystery@1` | an ending | 2 or more, one `true` | fixed |
| `romance-companion@1` | a date or a segment | 0 or more | fixed |

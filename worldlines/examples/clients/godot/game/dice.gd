# Checks the narrator writes into the prose — "[调查员 说服(问出钥匙): 96 > 35] → 大失败" — lifted out and rolled on screen.
extends RefCounted

const GOOD := ["大成功", "成功", "success", "critical", "성공", "成功した"]
const BAD := ["失败", "fumble", "failure", "失敗", "실패"]

var _re := RegEx.create_from_string("\\[([^\\s\\]\\[]+) ([^(\\]\\[]+?)\\(([^)]*)\\): (\\d+) (>|<|≤|<=|≥|>=) (\\d+)\\] → ([^\\s\\n]+)")


## {rolls: [{who, skill, why, roll, op, target, outcome, good}], rest: prose without the lines}
func lift(text: String) -> Dictionary:
	var rolls := []
	for m in _re.search_all(text):
		var outcome := m.get_string(7)
		var good := false
		for g in GOOD:
			if outcome.contains(g):
				good = true
		for b in BAD:
			if outcome.contains(b):
				good = false
		rolls.append({"who": m.get_string(1), "skill": m.get_string(2).strip_edges(), "why": m.get_string(3), "roll": int(m.get_string(4)),
			"op": m.get_string(5), "target": int(m.get_string(6)), "outcome": outcome, "good": good})
	var rest := _re.sub(text, "", true)
	while rest.contains("\n\n\n"):
		rest = rest.replace("\n\n\n", "\n\n")
	return {"rolls": rolls, "rest": rest}

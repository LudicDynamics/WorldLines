# Soul Agent Contract — chara

1 soul = 1 agent(M30). 쓰기 범위 = manifest.json의 `write_globs`
(soul은 자기 context만 고친다. 범위를 벗어난 쓰기는 apply 파이프라인이 거부한다).
prompt 계약: 엔진 기본 system.md 템플릿을 쓰며, 이 soul의
`agents/soul-agent/system.md`로 덮어쓸 수 있다.

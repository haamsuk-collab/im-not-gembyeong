# im-not-gembyeong

제미나이, 더 이상 젬병이 아니(고 싶)다.

젬병은 "그 일에 영 서툴다"는 말이고 발음이 제미나이와 묘하게 닮았습니다. Gemini, show the receipt.

English version: [README.md](README.md)

코드와 명령과 문서에서는 이 프로그램을 G1이라고 부릅니다. (이 이름도 말장난입니다. g 하나, Antigravity가 떼어 버린 바로 그
중력입니다.) G1은 Gemini가 코드를 만지는 동안 Antigravity CLI(`agy`) 옆에서 같이 도는 작은 프로그램입니다. 하는 일은 하나뿐입니다.
"다 됐습니다"가 정말 다 된 것인지 확인하고, 세션이 죽어도 일은 살려 둡니다. 표준 라이브러리만 쓰는 Python 약 4,700줄(`wc -l`
기준)이고 의존성은 없으며 프로젝트 디렉터리 안에는 파일 하나 쓰지 않습니다.

한 번 설치하면 그 뒤로는 모든 프로젝트에서 손댈 일이 없습니다.

## 문제는 문장 하나입니다

"완료했습니다. 테스트가 통과합니다."

이 문장이 틀릴 수 있는 방식은 둘이고 둘 다 직접 재 보았습니다. 도구 호출을 막아 두었는데도 Gemini 3.8 Flash는 8번 중 3번
"DONE"이라고 답했습니다. 아무것도 하지 않았는데도요(`research/agy-hooks/`). 그리고 세션이 끝나면 agent의 기억도 같이 끝나므로
다음 세션은 무엇을 했는지, 무엇이 남았는지, 애초에 "완료"가 무슨 뜻이었는지 모른 채 0에서 시작합니다.

자기 시험지를 자기가 채점하는 학생은 채점자가 아닙니다. G1은 심판입니다. 정답지를 쥐고 시험을 직접 돌리고 결과는 아무도 고칠 수
없는 장부에 적습니다.

## 알아 둘 단어 넷

| 단어 | 코드에서의 실체 |
|---|---|
| **contract(계약)** | 일을 시작하기 전에 적어 두는 "완료"의 정의. 목표, 기준, 검사, agent가 고쳐도 되는 경로(`allowed_paths`), 검사가 읽는 파일(`oracle_files`). ledger의 `contract_registered` 기록 안에 통째로 들어 있음 |
| **receipt(영수증)** | `verification_succeeded` 기록. G1이 직접 돌린 검사와 종료 코드, 트리 해시, 환경 해시, 바뀐 경로 목록. 완료는 이 기록의 순번과 해시에 묶임 |
| **ledger(장부)** | 추가만 되는 JSONL 파일. 모든 기록이 바로 앞 기록의 SHA-256을 품음. `~/.g1/workspaces/<id>/`에 있음 |
| **projection(투영)** | G1이 모델의 문맥에 주입하는 상태 블록. 세션 시작 때 1,024바이트, 모델 호출 전마다 512바이트. 재료는 ledger뿐 |

G1의 나머지는 전부 이 넷 중 하나를 섬깁니다.

## 어디에 끼어드는가

`agy`는 agent를 루프로 돌립니다. 모델을 부르고, 모델이 시킨 도구를 돌리고, 반복하고, 멈춥니다. 이 루프의 정해진 순간에 외부
명령을 실행하고 stdin으로 JSON payload를 준 뒤 stdout의 JSON을 답으로 읽습니다. 이 순간이 hook입니다. G1은
`~/.gemini/config/hooks.json`에 `g1` 그룹으로 항목 넷을 설치합니다.

| 이벤트 | 시점 | G1이 하는 일 | 제한 시간 |
|---|---|---|---|
| `SessionStart` | 대화마다 한 번(subagent 포함) | 처음 보는 workspace면 등록, ledger를 anchor와 대조, `agy` 바이너리 지문 확인, 자기 규칙 파일이 바뀌었으면 복원, projection 주입 | 30초 |
| `PreInvocation` | 모델 호출 전마다 | 대기 중인 proposal 검증(호출당 red baseline 최대 둘), blocked와 resume 보고 적용, 512바이트 상태 블록 주입 | 900초 |
| `PreToolUse` | 쓰기 도구 실행 전 | 호출을 journal에 기록. G1 파일, transcript, 고정된 oracle, 범위 밖 경로에 쓰는 호출 거부. G1 상태를 지목하거나 G1 명령줄을 실행하는 셸 명령 거부 | 20초 |
| `Stop` | agent가 멈출 때 | 코드 사본에서 contract의 검사 실행, canary 실행, 트리 비교, receipt 기록, 판정(완료, 한 턴 더, 보류) | 1800초 |

`PreToolUse`의 matcher는 쓰기 도구 이름만 고른 정규식입니다(`write_to_file`, `replace_file_content`, `run_command`,
`invoke_subagent`와 그 친척들). 파일 보기나 검색은 G1 프로세스를 띄우지 않습니다. 읽기는 공짜입니다. 원래 그래야 합니다.

hook 항목 하나하나는 작은 인라인 Python 프로그램입니다. `~/.g1/g1.pyz`를 해시해서 설치 때 고정한 값과 비교하고 다르면 종료
코드 3으로 끝납니다. 그래서 손을 댄 G1은 그 세션이 끝날 때까지 아예 실행을 거부하고, `agy`는 `PreToolUse`의 실패를 거부로
치므로 누가 다시 설치할 때까지 쓰기 도구가 전부 막힙니다. 재 보고 일부러 고른 동작입니다.

## 과제 하나, 처음부터 끝까지

프로젝트에 틀린 `median()`과 실패하는 테스트가 있습니다. 사용자의 지시는 *"src/stats.py를 고쳐서 tests/test_stats.py를
통과시켜"*가 전부입니다. G1이라는 말은 아무도 하지 않았습니다.

1. **세션 시작.** G1은 이 프로젝트를 처음 봅니다. `~/.g1/workspaces/<경로의 sha256>/`에 genesis 기록 하나짜리 ledger를
   만들고 이렇게 주입합니다. *진행 중인 contract 없음. 오래 남을 일이라면 `.../proposals/<id>.json`에 proposal을 쓰시오.*
   형식은 `views/PROPOSAL_FORMAT.md`와 설치된 skill에 있습니다.

2. **proposal(제안서).** agent가 JSON 파일 하나를 씁니다.

   ```json
   {
     "task": "fix-median",
     "objective": "median() returns the middle value for odd-length lists",
     "criteria": [{"id": "C1", "text": "tests in tests/test_stats.py pass"}],
     "checks": [{"id": "K1", "argv": ["python3", "-m", "pytest", "tests/test_stats.py", "-q"],
                 "kind": "must_flip", "covers": ["C1"], "targets": ["src/stats.py"], "timeout_s": 120}],
     "allowed_paths": ["src/"],
     "oracle_files": ["tests/test_stats.py"]
   }
   ```

3. **검증, 다음 모델 호출 전에.** G1은 파일 이름을 `fix-median.running.json`으로 바꾸고 lock을 잡은 뒤 그 descriptor로만
   읽습니다. 이름으로 다시 열지 않으므로 agent가 중간에 내용을 바꿔치기할 수 없습니다. 그다음 순서대로 봅니다.
   - 모양. 엄격합니다. 모르는 키 하나면 통째로 거부. id는 `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, 문장은 600자 이하, 검사는 64개
     이하, 경로는 상대 경로이며 `.`도 `..`도 안 됩니다.
   - 커버리지 행렬. 모든 기준에 검사가 하나 이상, 모든 검사는 기준을 하나 이상 덮어야 합니다. 사람만 확인할 수 있는 기준은
     빈 행이고 거부됩니다.
   - target. `must_flip` 검사는 자기가 의존하는 파일을 모두 적습니다. `allowed_paths` 안에 있어야 하고 oracle 파일이면 안
     됩니다.
   - 상태. 이 workspace에 진행 중인 다른 contract가 없어야 하고 `depends_on`의 과제는 모두 완료 receipt가 있어야 합니다.
   - 고정. oracle 파일 각각의 SHA-256, 검사가 부르는 실행 파일 각각의 SHA-256(`python3`은 agent의 PATH가 아니라 깨끗한
     PATH에서 찾습니다).
   - **red baseline(빨간 기준선).** 트리를 `~/.g1/scratch/baseline-*/tree`로 복사해 검사를 전부 돌립니다. `must_flip`
     검사는 지금 반드시 실패해야 합니다. 이미 통과하는 검사는 한 일을 전혀 증명하지 못하므로 거부합니다. `guard` 검사는
     지금도 통과하고 끝날 때도 통과해야 합니다.
   - 기준 manifest. 파일마다 해시, 모드, 크기를 적은 트리 전체. 나중에 바뀐 파일을 가려낼 때 씁니다.

   답은 파일 옆에 `fix-median.accepted.json`이나 `fix-median.rejected.json`으로 놓이고 이유가 유형별로 적힙니다. 수락되면
   ledger에 `contract_registered` 기록이 들어갑니다. contract 본문, baseline 결과, oracle 해시, 실행 파일 해시, 트리 해시가
   함께 들어갑니다.

4. **작업.** agent가 `src/stats.py`를 고치고 테스트를 마음껏 돌립니다. 파일 도구로 `tests/test_stats.py`를 고치려 하면
   `PreToolUse`가 거부합니다. *G1 pinned oracle.* `README.md`를 건드리면 *G1 scope.* 셸에서 `sed -i`로 테스트 파일을
   고치면 일부러 통과시킵니다. agent는 자기 테스트를 돌릴 수 있어야 하기 때문입니다. 대신 나중에 해시로 잡습니다.

5. **멈춤.** `agy`가 `fullyIdle: true`를 보고합니다. G1은 이제 이렇게 합니다.
   - ledger의 head를 anchor와 대조합니다. 어긋나면 workspace를 잠그고 아무것도 돌리지 않습니다.
   - oracle 해시를 고정값과 비교합니다. 다르면 `oracle_changed`로 시도가 끝납니다.
   - 호스트 transcript에 적힌 쓰기 도구 호출 수를 자기 journal과 비교합니다(`observation_gap`).
   - 실행 파일을 다시 해시합니다(`executable_changed`).
   - 트리를 임시 디렉터리로 복사합니다. `.git`, `node_modules`, `.venv` 같은 디렉터리는 빼고 HOME과 TMPDIR은 전용으로,
     PATH는 허용 목록으로, `LANG=C.UTF-8`, `PYTHONHASHSEED=0`으로 둡니다.
   - 거기서 검사를 전부 돌립니다. 검사마다 자기 프로세스 그룹, 제한 시간, 출력 스트림당 1 MiB 상한. 종료 코드 0, 시간 초과
     없음, 잘림 없음이면 통과입니다.
   - **canary(카나리아)**를 돌립니다. 통과한 `must_flip` 검사마다 사본을 하나 더 떠서 그 검사의 target을 파싱 불가능한
     바이트로 덮어쓰고 다시 돌립니다. 이번에는 반드시 실패해야 합니다. 코드 없이도 통과하는 검사는 코드를 검사하는 것이
     아닙니다.
   - 트리를 다시 해시합니다. 검사 전 해시와 같아야 합니다(`identity_changed`).
   - 트리를 기준 manifest와 비교합니다. `src/stats.py`만 바뀌었습니다. `allowed_paths` 밖에서 바뀐 경로나 workspace 밖을
     가리키는 새 symbolic link는 `scope_violation`입니다.
   - 증거를 `evidence/<attempt>/results.json`에 씁니다. API key, PEM 블록, JWT, bearer token은 먼저 지웁니다.
   - ledger에 `verification_started`와 `verification_succeeded`를 추가합니다.

6. **완료, lock 하나 안에서.** G1은 ledger lock을 잡고 receipt 뒤에 다른 기록이 없는지 확인하고 트리를 해시하고
   `complete.approve()`를 부르고 트리를 다시 해시한 뒤 head에 compare-and-swap으로 `task_status_changed: complete`를
   receipt에 묶어 추가합니다. 그 사이에 무엇이든 움직였으면 이번 턴에는 완료하지 않고 다음 턴에 다시 검증합니다. 기록 뒤에
   한 번 더 해시합니다. 그 몇 마이크로초 틈의 변경은 막지 못하지만 `post_completion_change`로 기록하고 보여 줍니다.

7. agent의 마지막 말은 "median을 수정했습니다"였습니다. 위 과정 어디에도 그 문장은 입력으로 들어가지 않았습니다. 듣기에는
   좋았습니다만.

## 완료 함수

`complete.approve()`는 함수 하나이고 "완료"가 나오는 유일한 자리입니다. 아래가 전부 성립할 때만 예라고 합니다.

- 모든 검사가 executed 표시와 함께 통과했고 모든 `must_flip` 검사에 민감한 canary가 있음
- receipt가 contract의 모든 검사를 덮음(빈 벡터는 "전부 통과"가 아님)
- 지금 트리 해시가 receipt의 해시와 같음
- receipt의 contract 해시가 과제의 것과 같음
- oracle 해시가 고정값과 같음
- policy 해시(G1 버전, 코드 해시, hook 그룹 해시)가 등록 때 봉인한 값과 같음
- 바뀐 경로가 모두 허용 경로 안
- 관측 gap이 0
- 과제가 아직 active

다른 모든 입력은 veto로 타입이 정해져 있습니다. 아니오의 이유를 보탤 수는 있어도 예를 보탤 수는 없습니다. 테스트 하나가 veto
입력의 모든 조합을 나열해 실행된 증거 없이는 어떤 조합도 승인하지 못함을 보입니다. 모델의 의견은 agent 자신의 흐뭇한 요약을
포함해 이 함수의 시그니처에 없습니다.

## 검사가 통과하지 못하면

agent를 멈추게 둘지 한 턴 더 시킬지 정해야 합니다. `control.decide()`는 ledger만 보는 순수 함수입니다.

| 상황 | 판정 |
|---|---|
| 지난 실패 뒤로 트리가 안 바뀜 | 보류, `no_change`. 검증을 돌리지 않음 |
| 검증을 돌릴 수 없었음(oracle 변경, 디스크 부족, 실행 파일 없음, gap) | 멈춤, `environment_unknown`. 진전도 실패도 아님 |
| 범위 밖 변경 | 보류, `scope_violation` |
| 같은 트리와 결과 조합을 전에 봤거나 결과가 A B A B로 번갈아 나옴 | 보류, `oscillation` |
| 이 과제에 이미 세 번 이어 감 | 보류, `budget_exhausted` |
| 실패하는 검사의 집합이 진부분집합으로 줄지 않음 | 보류, `no_progress` |
| 그 외 | `continue`. 한 줄로 통과한 검사 수, 다음 실패 검사와 그 정확한 명령 |

이어 가기 횟수는 답을 출력하기 전에 ledger에 쓰고 절대 줄지 않습니다. 검사의 원본 출력은 모델 문맥에 되돌려 주지 않습니다.
`agy` 자체는 세션당 열 번까지 continue를 허용하지만 G1은 과제당 세 번까지만 씁니다. 강제로 열 번 이어 가게 했더니 답 하나의
26배를 쓰면서 군말만 늘었기 때문입니다.

보류된 과제가 죽은 것은 아닙니다. 같은 task id로 새 proposal을 쓰면 red baseline을 새로 돌리고 대체합니다. agent가
`<task>.blocked.json`(확인 못 한 항목 하나, 이유, 선택지)으로 스스로 멈춘 과제는 `<task>.resume.json`으로 같은 contract
아래 이어집니다. 다음 세션의 projection이 그 질문을 품고 가므로 새 agent는 다시 추측하는 대신 사용자에게 묻습니다.

## 기록을 믿을 수 있는 이유

**사슬.** 기록 하나는 `{"schema", "seq", "prev", "ts", "event", "data", "hash"}`입니다. 정규 인코딩(UTF-8, 키 정렬, float
금지, 중복 키 금지, 꼬리 데이터 금지)으로 직렬화하고 도메인 접두어를 붙여 해시합니다. 어디든 한 바이트만 바뀌면 그 뒤 해시가
전부 어긋납니다. `g1 audit`은 사슬을 걷고 검사별 결과에서 receipt의 판정을 다시 계산하고 완료마다 완료 함수를 다시 돌리며
증거보다 후한 판정이 저장돼 있으면 지적합니다.

**commit.** lock(`flock`, 10초 제한, inode 재확인) 아래 이 순서로 합니다. 기록을 `ledger.pending.json`에 journal, 추가, head
이동, anchor 이동, mirror에 추가, journal 삭제. 어디서 죽든 다음에 ledger를 열 때 journal로 마무리하거나 버립니다. 줄 중간에서
끊긴 추가는 journal의 바이트로 채웁니다. commit된 바이트는 절대 지우지 않습니다.

**anchor, mirror, witness.** workspace 디렉터리 밖에 G1은 마지막으로 쓴 head(`~/.g1/anchors/<ledger_id>.head`), 모든 기록의
사본(`~/.g1/mirror/<ledger_id>.jsonl`), workspace마다 어느 ledger가 사는지(`~/.g1/anchors/ws/<id>.json`)를 둡니다. 세션 시작
때마다 그리고 검증 전마다 head는 anchor와 같아야 합니다. anchor보다 뒤처진 ledger는 기록을 잃은 것이고 mirror에서 되살리며 그
수리를 기록합니다. anchor보다 앞서거나 다른 ledger는 G1 밖에서 바뀐 것입니다. workspace를 잠그고 쓰기 도구를 전부 거부하며
사용자가 `g1 repair --accept-ledger`, `--restore`, `--forget` 중 하나로 결정합니다. 복원은 anchor로 경계를 치므로 누군가
mirror에 덧붙인 기록이 깨끗한 역사로 돌아오지 않습니다.

**자기 방어.** hook 항목이 코드 해시를 고정합니다(위). 세션 시작 때마다 규칙 파일 다섯과 skill을 manifest와 다시 대조해 바뀐
것은 되돌립니다. `agy` 바이너리의 지문(크기와 앞뒤 1 MiB)을 찍고 바뀌었으면 `host_contract_observed: unverified`를 기록한 뒤
사용자가 probe를 다시 돌리고 `g1 host-verify`를 할 때까지 완료를 보류합니다. G1의 결정 명령(`install`, `uninstall`, `init`,
`propose`, `turn-end`, `host-verify`, `repair`, `challenge`, `challenges --run`)은 `/proc`을 읽어 조상 프로세스에 `agy`가
있으면 실행을 거부합니다. `/proc`을 읽을 수 없으면 모름을 agent로 칩니다.

**agent의 말.** G1이 호스트 transcript를 읽는 목적은 하나입니다. 모델의 쓰기 도구 호출을 세어 자기 hook이 journal에 적은 수와
맞추는 것입니다. 차이가 있으면 gap이고 gap은 완료를 거부합니다. transcript가 사라졌으면 receipt와 상태 블록에
`liveness_unknown`으로 적되 완료를 거부하지는 않습니다. 지워진 세션이 새 agent의 이어 가기를 막아서는 안 되기 때문입니다.

## 문지기, 그리고 일부러 열어 둔 문

모든 gate는 결정적이고 이름이 있습니다. 셸 명령을 이해하려 드는 gate는 없습니다. 그래야 합니다.

호출 전에 거부하는 것:

- 파일 도구로 `~/.g1` 아래, hooks 파일, G1 규칙과 skill, workspace의 `.agents/hooks.json`에 쓰기(workspace의 `proposals/`와
  `challenges/`는 예외입니다. 거기는 agent가 쓰는 자리입니다)
- 파일 도구로 `agy`의 대화 저장소나 `.system_generated` 아래에 쓰기
- contract가 진행 중일 때 파일 도구로 고정된 oracle이나 `allowed_paths` 밖에 쓰기
- 위 경로를 본문에 지목하거나 명령 위치에서 G1 명령줄을 실행하는 셸 명령(`g1`, `g1.pyz`, `python -m g1`,
  `python -c 'import g1'`, 그리고 `sudo`, `env`, `exec`, `nice`, `timeout`, `sh -c`, `eval`, here-document 뒤에 숨은
  것까지, 하위 명령 불문). 앞 16 KB는 `shlex`로 토큰화하고 나머지는 선형 패턴으로 훑으며 1 MiB를 넘는 명령은 그냥 거부합니다.
- 무결성 lockdown 뒤에는 전부

일부러 거부하지 않는 것: 셸로 일반 파일이나 고정된 oracle을 고치는 일. agent는 자기 테스트를 돌릴 수 있어야 합니다. receipt가
나중에 oracle 해시까지 포함해 트리 전체를 재므로 그 수정은 중요한 자리에서 잡힙니다. 텍스트 gate는 걸림줄이지 담장이 아닙니다.
담장은 해시 대조, anchor 대조, 그리고 agent가 띄운 프로세스를 명령줄 스스로 거부하는 것입니다.

## 두 번째 모델을 검토자로

모델의 검토도 여느 주장과 같은 주장입니다. G1은 검토자의 지적을 한 가지 모양으로만 받습니다. **challenge**, 즉
`challenges/<id>.json` 파일에 든 주장 하나와 contract 하나. 그 contract의 `must_flip` 검사는 지금 트리에서 그 결함 때문에
실패해야 합니다. 검토자는 보통 다른 계열의 모델이 자기 `agy` 세션에서 맡습니다.

hook에서는 아무것도 돌지 않습니다. 사용자가 목록을 보고(`g1 challenges .`, 파싱만 하고 실행은 하지 않으며 검사마다 argv
전체를 표시) 명령을 읽은 뒤 자기 권한으로 돌립니다(`g1 challenges . --run`). 검사마다 60초입니다. 실제 트리는 전후로
해시하며 트리를 바꾼 검사는 challenge를 `invalid`로 만듭니다. 전부 실패하면 `confirmed`, 하나라도 통과하면 `unproven`입니다.
confirmed된 challenge는 사용자를 기다립니다. `g1 challenge . <id> accept`가 red baseline을 다시 돌리고 결정과 contract를
기록 하나로 등록하며 `reject`는 이유를 기록합니다. 결정이 사용자의 몫인 이유가 있습니다. 실패하는 검사가 증명하는 것은 "그
동작이 없다"이지 "검토자의 기대가 옳다"가 아니기 때문입니다. 수락 뒤는 보통 작업입니다. 작업 모델이 고치고 G1이 검증하고
receipt가 완료합니다.

끝까지 한 번 재 보았습니다. Flash가 SemVer 라이브러리를 만들었고(숨은 oracle 44개 중 43개 통과), Claude Opus 5.5가 빠진
하나를 실패하는 검사로 73초 만에 증명했으며 거짓 보고는 없었고, 사용자가 수락했고, Flash가 receipt 아래에서 고쳤습니다(44개
중 44개).

## 설치

```sh
git clone https://github.com/haamsuk-collab/im-not-gembyeong ~/src/g1
~/src/g1/bin/g1 install
```

이 두 줄은 직접 치십시오. installer는 결정 명령이어서 `/proc`을 읽고 조상 프로세스에 `agy`가 있으면 종료 코드 3으로
거부합니다. 심판을 임명하는 일은 선수의 몫이 아닙니다. agent에게 설치를 시키면 거부 사유 한 줄을 받고 사용자에게 부탁하는
수밖에 없습니다.

installer가 쓰고 그 뒤로 계속 지키는 파일:

| 경로 | 역할 |
|---|---|
| `~/.g1/g1.pyz` | G1 코드. bytecode만 든 zipapp(표준 라이브러리만, 의존성 없음). 소스 컴파일을 생략해 hook당 15~25 ms 절약 |
| `~/.g1/manifest.json` | 코드 해시, hook 그룹과 그 해시, 호스트 지문, 설치한 규칙 파일들의 해시 |
| `~/.gemini/config/hooks.json`의 `g1` 그룹 | hook 항목 넷, 각각 코드 해시 고정. 다른 도구의 항목은 바이트 그대로 보존 |
| `~/.gemini/config/rules/g1.md`, `g1-instinct.md` | 항상 켜진 규칙 둘. 진입 규칙(권위의 순서, 다섯 의무, 동작 방식)과 본능 규칙(확인하거나 멈추기, 채널별 권위, 증거, 정직한 마지막 답) |
| `~/.gemini/config/rules/g1-work.md`, `g1-writing.md`, `g1-korean.md` | 상황별 규칙. 코딩 전, 문서 작성 전, 한국어 작성 전에 모델이 읽음 |
| `~/.gemini/config/skills/g1/SKILL.md` | proposal 형식의 항목별 설명, blocked와 resume 보고, challenge, Stop에서 G1이 하는 일 |
| `~/.g1/workspaces/<id>/` | 프로젝트마다 하나, 첫 세션에 생성. `ledger.jsonl`, `ledger.head.json`, `proposals/`, `challenges/`, `evidence/`, `views/` |
| `~/.g1/anchors/`, `mirror/`, `observe/`, `scratch/` | anchor와 witness, ledger 사본, hook journal과 lockdown 표지, 검사용 임시 사본 |

프로젝트 안에는 아무것도 쓰지 않습니다. workspace의 `.agents/hooks.json`에 G1 그룹이 있었다면 installer가 지웁니다. 층은
하나, 전역 hooks 파일뿐입니다. 두 층을 두었더니 비용이 두 배가 되고 서로 본 것이 달랐습니다. 누군가 hook 항목이나 규칙이나
skill을 바꾸면 다음 세션이 되돌립니다. `~/src/g1/bin/g1 uninstall`은 G1의 항목만 지우고 `--purge`를 붙이면 `~/.g1`도
지웁니다.

명령은 모두 선택입니다.

```sh
~/src/g1/bin/g1 status .       # G1이 아는 이 프로젝트의 상태: head, active 과제, alert, 과제 목록
~/src/g1/bin/g1 audit .        # 사슬을 걷고 모든 receipt와 완료를 다시 계산
~/src/g1/bin/g1 repair .       # lockdown 뒤: 무엇이 다른지 본 다음 --accept-ledger, --restore, --forget
~/src/g1/bin/g1 challenges .   # challenge 목록. --run [ID ...]이면 그 검사를 사용자 권한으로 실행
~/src/g1/bin/g1 challenge . ID accept|reject [REASON]
~/src/g1/bin/g1 host-verify    # 새 agy 버전에서 probe를 다시 돌린 뒤
~/src/g1/bin/g1 turn-end .     # Stop hook이 하는 일을 손으로 한 번
```

launcher는 설치된 archive를 우선 쓰고 없으면 소스 트리로 떨어집니다. `install`만은 항상 옆의 소스 트리에서 빌드합니다.

## 비용, 잰 값

gemini-3.8-flash-high로 실제 `agy` 세션 137개(그중 하나는 Claude Opus 5.5가 검토자)를 돌렸습니다. 아래 숫자는 모두 독립
oracle이 냈습니다. 실행기가 최종 트리에서 원래 테스트를 다시 돌리거나 트리를 직접 확인했고 G1도 agent도 결과를 제공하지
않았습니다.

| 질문 | 답 |
|---|---|
| G1이 agent를 느리게 하는가 | 쓰기 도구 호출 75 ms(그중 G1 자체 작업은 5 ms), 모델 호출 96 ms, 읽기 전용 호출 0 ms. 검증은 턴당 한 번, 0.3~1.1초 |
| 판정이 맞는가 | 46세션 중 46세션에서 G1의 "완료"가 oracle과 일치. 거짓 완료 없음 |
| 일이 줄어드는가 | 쉬운 과제와 중간 과제: 토큰 17~24% 감소, 시간 23~32% 감소. 어려운 단일 세션 과제: 차이 없음 |
| 세션이 사라지면 | 세션을 죽이고 기록을 지운 뒤, 다음 세션이 토큰 39% 적게, 도구 호출 33번 대신 14번으로 마침. 과제를 다시 찾아낼 필요가 없었음 |
| 두 번째 모델이 Flash가 놓친 것을 찾는가 | 한 번 끝까지, 위에 적은 대로 |
| 본능 규칙이 행동을 바꾸는가 | 모호하거나 불가능한 과제 여섯에서 Flash는 규칙이 있을 때 12세션 중 12세션, 없을 때도 12세션 중 12세션 멈추고 물었음. 이 부류에서는 측정되지 않고 측정되는 비용도 없음 |

재지 못한 것: 과제가 자족적이고 테스트가 보일 때 Gemini 3.8 Flash는 60세션 동안 한 번도 실패하지도 거짓말하지도 않았습니다.
심판이 가장 필요한 큰 저장소와 며칠짜리 작업은 아직 이 데이터에 없습니다. 세부와 한계는 `docs/design.md` 14절과
`research/measure/`에 있습니다.

## 사람들이 하는 불평

무엇이 잘못되는지 추측하고 싶지 않아서 Threads와 X에서 Gemini에 관한 글 909개를 읽었습니다(한국어와 영어, 검색어 187개,
2023년 12월부터 2026년 10월까지). 그중 343개가 사용자 자신의 불만입니다. 대부분은 G1이 손댈 수 없는 것입니다. 멍청해졌다(99),
제품(90), 장애(74), 경쟁 모델(61), 요금(54). G1이 직접 답하는 네 꼬리표, 거짓 보고, 지시 무시, 맥락 상실, 반복은 불만
343개 중 57개에, 코드를 다루는 agent에 관한 불만 86개 중 18개에 나타납니다. 점수가 아니라 지도로 읽으십시오. 방법과 집계와
링크는 `research/complaints/`에 있습니다.

## 코드는 어떻게 검토되었는가

독립 리뷰 다섯 번, 각각 `agy` 안의 Gemini 3.8 Flash 세션에 서면 지침을 준 것입니다. 다섯 번째 전에는 Claude Opus 5.5와 Claude
Fable 5.1이 같은 코드를 `agy` 밖에서 읽었습니다. 모든 지적은 검토자 자신의 스크립트로 재현한 뒤에 고쳤고 모든 수정에는 지적의
이름을 붙인 테스트가 있습니다. 다섯 번째 리뷰는 아무것도 찾지 못했습니다. 지침, 보고서, 답변은 `research/review/`에 있습니다.
테스트는 `tests/test_core.py`에 126개입니다.

## G1이 하지 않는 것

- 모델을 더 똑똑하게 만들지 않습니다. 유감입니다만. prompt도 도구도 루프도 그대로 둡니다.
- 두 번째 모델을 판사로 쓰지 않습니다. 판사는 설득하면 예라고 하지만 테스트는 설득이 통하지 않습니다.
- `agy`의 기능을 대체하지 않습니다. subagent, goal mode, 병렬 시도는 그대로 두고 결과만 검증합니다. subagent의 도구 호출은
  자기 conversation id로 같은 hook을 탑니다.
- agent가 한 세션 안에서 셸로 G1의 파일, anchor, witness, mirror, manifest를 전부 일관되게 다시 쓰면 막지 못합니다. G1
  전체가 사용자 권한으로 돌기 때문입니다. 부분적인 변조와 구조화된 도구를 통한 모든 변조는 잡아내고, G1을 지운다고 거짓
  완료가 생기지는 않습니다. 완전한 방어에는 이 환경(PRoot 위의 Termux)이 주지 않는 OS 경계가 필요합니다. 이 잔존 위험은
  `docs/design.md` 7.7절에 적혀 있습니다.

## 더 읽을 곳

| 문서 | 내용 |
|---|---|
| `docs/principles.md` | G1의 바탕이 된 여덟 원칙과 각각이 규칙이 된 과정 |
| `docs/design.md` | 전체 설계: 모든 장치와 각각이 증명하는 사실과 유래 |
| `docs/host-agy.md` | `agy`의 hook을 측정한 결과, 문서가 틀린 지점 포함 |
| `research/complaints/` | 불만 조사: 방법, 플랫폼과 언어별 집계, 꼬리표별 글 링크 |
| `research/agy-hooks/` | hook 측정의 probe와 원본 기록 |
| `research/measure/` | A/B 실행기, 여섯 측정 전부의 결과, 실험 C1(challenge) |
| `research/review/` | 독립 리뷰 다섯 번과 검토자 둘의 사전 감사, 모든 지적의 재현과 수정 |
| `research/atoms/` | 이전 하네스 하나, 다른 프로젝트 다섯, 글 연재 하나에서 가져온 설계 "atom" 696개와 각각의 판정 |

## 저장소 지도

```
src/g1/           핵심: canon, ledger, snapshot, contract, runner, verify, complete, control, state,
                  project, workspace, integrity, audit, install, paths
src/g1/adapter/   agy.py, 호스트의 이름을 아는 유일한 모듈
src/g1/host/      G1이 ~/.gemini/config에 설치하는 규칙 다섯과 skill
tests/            테스트 126개: 사슬 끊김, 충돌 복구, 완료 함수, gate, canary, anchor, challenge, 검토자의 모든 지적
bin/g1            명령줄 launcher
docs/             원칙, 설계, 호스트 계약
research/         불만 조사, hook probe, A/B 실행, 리뷰, 설계 atom
```

## 라이선스

MIT. `LICENSE` 참조.

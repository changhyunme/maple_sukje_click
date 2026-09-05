# Maple 숙제 자동화

macOS의 BlueStacks Air에서 반복되는 일일 숙제를 세 인스턴스에 순차 실행하는
개인용 UI 자동화 도구입니다. 고정 좌표만 연속으로 누르지 않고, 버튼 색상과
화면 변화량을 확인해 예상하지 못한 화면에서는 중단하도록 설계했습니다.

## 사용 전 준비 — 그대로 실행하지 마세요

이 저장소의 인스턴스 이름, 창 크기·배치, 화면 좌표와 판정값은 개발자의
macOS·BlueStacks 환경에 맞춰져 있습니다. 저장소를 받은 뒤 곧바로 실행하지 말고,
먼저 **Claude Code 또는 Codex에게 자신의 환경에 맞게 점검하고 수정해 달라고
요청한 뒤 사용하세요.** 수정 후에도 유료 재화가 없는 테스트 계정이나 한 개의
인스턴스에서 전체 흐름을 직접 확인한 다음 나머지 인스턴스로 확대하는 것을
권장합니다.

다음 요청문을 그대로 복사해 시작할 수 있습니다.

```text
이 저장소를 내 macOS와 BlueStacks Air 환경에 맞게 점검하고 수정해줘.
내 인스턴스 개수와 이름, BlueStacks 버전, 창 크기·위치, 화면 해상도,
게임 UI 좌표, macOS 접근성·화면 기록 권한, Python·FFmpeg 의존성을 확인해줘.
유료 상품, 보석, 소환권, 친구 일괄 전달은 절대 누르지 않도록 안전장치를
검토하고, 먼저 한 인스턴스에서 각 단계를 화면 변화로 검증한 뒤 실행 방법을 알려줘.
```

Claude Code나 Codex에 화면 캡처 또는 로그를 제공할 때에는 캐릭터명, 채팅,
계정 식별 정보 등 공개하고 싶지 않은 내용이 포함되지 않았는지 먼저 확인하세요.

> 이 프로젝트는 게임 또는 BlueStacks 운영사와 관련 없는 비공식 도구입니다.
> UI 자동화 사용 가능 여부와 계정 위험은 각 서비스의 최신 운영 정책을 직접
> 확인하세요.

## 주요 기능

- 성장 던전 5종 소탕
- 빠른 사냥 무료 보상, 일일 광고 부스터, 5분 반복 사냥
- 일반 상점의 무료 보상만 수령
- 무기·동료 무료 소환 보상만 수령
- 친구 보상 받기·보내기
- 길드 무료 업그레이드, 아레나 3회, 월드 보스
- 우편함·패스·일일 미션·이벤트 보상 수령(이벤트 목록 스크롤 포함)
- 완료 후 각 VM 메인 화면 캡처 및 이메일 보고
- BlueStacks 절전 화면 해제와 세 인스턴스 자동 탐색
- 화면 변화 및 버튼별 색상 신호를 이용한 클릭 검증

유료 상점 카드, 소환권·보석을 소비하는 일괄 소환, 친구 일괄 전달은 자동화
대상에서 제외합니다. 빠른 사냥의 보석 구매 탭에서는 결제가 아니라 해당 탭에
표시되는 무료 보상만 전용 `FREE` 배지를 확인한 뒤 수령합니다.

## 요구 사항

- macOS
- BlueStacks Air의 `Tiramisu64`, `Tiramisu64_1`, `Tiramisu64_2` 인스턴스
- Python 3.10 이상
- FFmpeg
- Python에서 `Quartz`를 제공하는 PyObjC
- 터미널 또는 Python 실행 앱에 부여된 macOS 접근성·화면 기록 권한

예시 설치:

```bash
brew install ffmpeg
python3 -m pip install pyobjc-framework-Quartz
```

## 실행

세 BlueStacks 인스턴스를 실행하고 게임 필드 화면까지 진입한 뒤 다음 명령을
사용합니다.

```bash
python3 full_flow_runner.py
```

전체 숙제가 끝나면 각 VM의 절전 화면을 해제하고 메인 화면을 캡처해 한 통의
완료 메일에 첨부합니다. 수신 주소와 Gmail SMTP 인증정보는 코드나 저장소에
기록하지 않고 환경변수로 전달합니다.

```bash
export MAPLE_REPORT_TO_EMAIL="받을주소@example.com"
export MAPLE_SMTP_USERNAME="발신Gmail주소@gmail.com"
export MAPLE_SMTP_APP_PASSWORD="Gmail 앱 비밀번호"
python3 full_flow_runner.py
```

기본 SMTP 서버는 `smtp.gmail.com:465`이며 필요하면
`MAPLE_SMTP_HOST`와 `MAPLE_SMTP_PORT`로 바꿀 수 있습니다. 메일 설정이 없거나
전송에 실패해도 이미 완료된 숙제 결과는 유지되고, 최종 JSON의
`completion_email`에 `skipped` 또는 `failed` 사유가 기록됩니다. 캡처와 메일을
이번 실행에서만 끄려면 `--no-completion-email`을 사용합니다.

인스턴스 자동 탐색 결과는 별도로 확인할 수 있습니다.

```bash
python3 -c 'from instance_registry import discover_instances; print(discover_instances())'
```

필요하면 PID를 직접 지정합니다.

```bash
python3 full_flow_runner.py --pids <AIR_PID> <AIR1_PID> <AIR2_PID>
```

주요 실행 옵션:

```text
--wait-seconds 300          반복 사냥 유지 시간
--world-boss-seconds 90     월드 보스 참여 시간
--verify-completed          길드·아레나·월드 보스를 반복하지 않고 나머지 화면 재검사
```

`--verify-completed`는 완전한 읽기 전용 모드가 아닙니다. 남아 있는 안전한 무료
보상은 수령할 수 있으므로 단순 화면 감사만 원할 때는 개별 화면을 직접 확인하세요.

## 개별 실행

각 작업은 하나의 BlueStacks PID를 받아 독립 실행할 수 있습니다.

```bash
python3 homework_runner.py <PID>
python3 booster_runner.py <PID>
python3 shop_runner.py <PID>
python3 summon_runner.py <PID>
python3 friend_runner.py <PID>
python3 guild_arena_worldboss_runner.py <PID>
python3 claim_runner.py <PID>
python3 event_runner.py <PID>
```

전체 순서와 복구 메모는 [RUNBOOK.md](RUNBOOK.md)에 정리되어 있습니다.

## 동작 방식과 안전장치

좌표는 BlueStacks 창 크기에 대한 비율로 계산됩니다. 각 클릭 전후의 관심 영역을
캡처해 자연스러운 화면 노이즈보다 큰 변화가 있었는지 검사하고, 무료 배지나 활성
버튼처럼 동작별 신호도 함께 확인합니다. Air2처럼 레이아웃이 다른 인스턴스에는
별도 좌표 프로필을 적용합니다.

게임 업데이트로 UI가 이동하면 안전 검증이 중단되거나 잘못된 요소를 감지할 수
있습니다. 업데이트 직후에는 한 인스턴스에서 좌표와 무료 상태를 먼저 확인하고,
무인 실행 전에 전체 흐름을 관찰하는 것을 권장합니다.

이벤트 창의 왼쪽 목록은 한 화면에 모두 표시되지 않을 수 있습니다.
`event_runner.py`는 현재 화면의 원형 알림점을 처리한 뒤 목록을 위로 드래그하고,
새 이벤트 본문이 더 이상 발견되지 않을 때까지 다시 탐색합니다. 직사각형 `NEW`
라벨은 보상 알림으로 보지 않으며, 유료 구매·선택형 누적 보상·청록색 바로가기는
자동으로 누르지 않습니다. 이벤트 UI가 크게 바뀐 날에는 스크롤된 아래쪽 목록까지
직접 확인한 뒤 자동 실행하세요.
현재 핑크빈 일일 미션은 이 동적 탐색으로 처리하며, `핑크빈 교환소`처럼 이벤트
재화를 소비하는 상점은 자동 구매 대상에서 제외합니다.

일일 중복 실행 방지를 위한 상태는 아래 로컬 파일에 기록되며 Git에서 제외됩니다.

```text
.homework_state.json
.booster_state.json
.friend_state.json
```

## 저장소 구성

```text
full_flow_runner.py                 전체 실행 순서 조정
homework_runner.py                  성장 던전
booster_runner.py                   빠른 사냥·부스터·반복 사냥
shop_runner.py                      무료 상점 보상
summon_runner.py                    무료 소환 보상
friend_runner.py                    친구 교환
guild_arena_worldboss_runner.py     길드·아레나·월드 보스
claim_runner.py                     우편함·패스·미션
event_runner.py                     이벤트 배지 탐색 및 안전 수령
ui_guard.py                         화면 변화 검증
mac_gesture.py                      macOS 창 탐색과 마우스 제스처
instance_registry.py                BlueStacks 인스턴스 탐색
```

`macro_actions.json`과 `macro_steps.jsonl`은 개발·복구 과정의 실행 감사 기록입니다.
자격 증명은 저장하지 않지만 과거 프로세스 ID, 에뮬레이터 로컬 포트, 창 위치 같은
환경 메타데이터를 포함합니다. 포크나 재배포 전에 필요에 따라 제거하거나 새 기록으로
교체하세요.

## 공개 및 보안 참고

스크립트는 게임 계정 비밀번호나 API 키를 요구하거나 저장하지 않습니다. 로컬 상태
파일과 Python 캐시는 `.gitignore`에 포함되어 있습니다. 새로운 화면 캡처나 실행
로그를 커밋할 때에는 캐릭터명, 채팅, 계정 식별 정보, 로컬 경로가 포함되지 않았는지
직접 확인하세요.

현재 별도 라이선스 파일은 없습니다. 저장소를 공개해도 자동으로 재사용·수정·배포
권한이 부여되는 것은 아니므로, 오픈 소스 배포를 원한다면 MIT 또는 Apache-2.0 등
목적에 맞는 라이선스를 추가하세요.

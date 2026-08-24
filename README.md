# Maple 숙제 자동화

macOS의 BlueStacks Air에서 반복되는 일일 숙제를 세 인스턴스에 순차 실행하는
개인용 UI 자동화 도구입니다. 고정 좌표만 연속으로 누르지 않고, 버튼 색상과
화면 변화량을 확인해 예상하지 못한 화면에서는 중단하도록 설계했습니다.

> 이 프로젝트는 게임 또는 BlueStacks 운영사와 관련 없는 비공식 도구입니다.
> UI 자동화 사용 가능 여부와 계정 위험은 각 서비스의 최신 운영 정책을 직접
> 확인하세요.

## 주요 기능

- 성장 던전 5종 소탕
- 빠른 사냥 무료 보상, 일일 광고 부스터, 5분 반복 사냥
- 일반·시그너스 상점의 무료 보상만 수령
- 무기·동료 무료 소환 보상만 수령
- 친구 보상 받기·보내기
- 길드 무료 업그레이드, 아레나 3회, 월드 보스
- 우편함·패스·일일 미션·이벤트 보상 수령
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

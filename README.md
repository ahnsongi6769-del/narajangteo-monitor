# 나라장터 모니터

조달청 나라장터 **용역 입찰공고**를 30분마다 자동으로 폴링해서, 3단계 필터(공고명 키워드 / 계약방식 / 지역)를 모두 통과한 **신규** 공고만 Microsoft Teams 채팅으로 알림 보냅니다.

GitHub Actions가 무료 한도 안에서 (월 ~220분) 알아서 돌립니다. 별도 서버 필요 없음.

---

## 동작 흐름

```
GitHub Actions (cron */30)
        │
        ▼
  최근 35분 윈도우로
  나라장터 API 호출  ─── 5xx/네트워크 오류 시 1·2·4초 백오프
        │
        ▼
  ┌─ 필터 1: 공고명 (대상 AND 행위) 또는 화이트리스트, 비IT 제외 ─┐
  ├─ 필터 2: 계약방식 (수의/지명 제외)                            ┤
  └─ 필터 3: 지역제한 (충청권 또는 전국)                          ┘
        │
        ▼
  seen.json 으로 중복 제거
        │
        ▼
  Teams Workflows 웹훅 POST (1초 간격)
        │
        ▼
  seen.json 자동 커밋·푸시
```

---

## 셋업

### 1. GitHub Secrets 등록

저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
| --- | --- |
| `NARA_API_KEY` | 공공데이터포털 인증키 **(Decoding 키)**. requests 라이브러리가 자동으로 URL-인코딩하므로 디코딩된 원본을 그대로 넣으세요. |
| `TEAMS_WEBHOOK_URL` | Teams Workflows에서 만든 "Post to a channel/chat when a webhook request is received" 트리거 URL. 본인 채팅으로 보내려면 채팅 대상이 자기 자신인 워크플로우를 만드세요. |

### 2. Actions 활성화

저장소 → **Actions** 탭 → 처음이라면 "I understand my workflows, go ahead and enable them" 클릭.

`.github/workflows/monitor.yml`이 자동 감지됩니다.

### 3. 수동 테스트 (선택)

Actions 탭 → **나라장터 모니터** → **Run workflow** 버튼.

첫 실행에서 인증키 오류가 나면 1~2시간 기다린 뒤 재시도하세요 (공공데이터포털 키 활성화에 시간이 걸립니다).

---

## 로컬 테스트

```powershell
# 1) 의존성 설치
pip install -r requirements.txt

# 2) .env 파일 생성 (.env.example을 복사해서 본인 값 채우기)
Copy-Item .env.example .env
# 그리고 .env 파일을 열어 NARA_API_KEY, TEAMS_WEBHOOK_URL 채우기

# 3) 실행
python -m src.monitor
```

### 디버그 모드 — 응답 필드 확인

지역제한·업종 필드명이 응답 스펙과 다를 수 있습니다. `.env`에 다음을 추가하면 첫 응답 항목의 모든 필드가 stdout에 pretty JSON으로 출력됩니다:

```
DEBUG_DUMP=1
```

출력을 보고 `src/filters.py`의 `REGION_FIELD_CANDIDATES` 튜플에 실제 필드명을 추가하세요.

---

## 필터 변경 방법

`config.yaml` 한 곳에서 모든 필터를 조정합니다.

```yaml
# 매칭 = ( (target 중 하나) AND (action 중 하나) ) OR (whitelist 중 하나)
#        AND  NOT (exclude_name_keywords 중 하나)
keywords_target:    [LMS, 홈페이지, 사이트, 포털, 웹, 시스템, 플랫폼, 앱, 어플]
keywords_action:    [구축, 개발, 제작, 고도화, 리뉴얼, 유지관리, 운영]
keywords_whitelist: [AI, RISE]
exclude_name_keywords: [공사, 토목, 건축, 교량, 도로, ...]   # 공고명에 있으면 제외

exclude_contract_keywords: [수의, 지명]    # 계약방식에 이 단어 들어가면 제외
allowed_region_names: [대전, 세종, 충북, 충청북도, 충남, 충청남도]
allow_no_region_restriction: true          # 지역제한 없는 공고도 알림
search_window_minutes: 35                  # API 윈도우
```

수정 후 커밋·푸시하면 다음 cron 실행부터 반영됩니다.

> 💡 키워드 매칭 예시
> - "LMS **고도화** 용역" → 통과 (LMS + 고도화)
> - "**AI** 챗봇 구축" → 통과 (AI 화이트리스트)
> - "교량 시스템 구축" → 제외 (`교량` 비IT 키워드)
> - "시스템 점검" → 제외 (action 키워드 없음)

---

## seen.json 동작

- 키: `{공고번호}-{차수}` 형식
- 값: 발송 시각 (ISO 8601, KST)
- 매 실행마다 **30일 이상 된 항목 자동 정리**
- 기본적으로 `.gitignore`에 들어있지만, 워크플로우의 `git add -f seen.json`으로 강제 커밋되어 다음 실행이 이어받을 수 있도록 함

로컬에서 seen.json을 추적하고 싶지 않으면 그대로 두세요. 저장소에 노출되는 게 싫지 않으면 `.gitignore`에서 `seen.json` 줄을 지워도 동작은 같습니다.

---

## 로그 예시

```
[START] 2026-05-14 14:30:00 KST
[API] 호출 윈도우: 202605141355 ~ 202605141430
[API] 응답 OK, 총 47건 수신
[FILTER:키워드] 47건 → 8건
[FILTER:계약방식] 8건 → 6건
[FILTER:지역] 6건 → 3건 (최종 신규 후보)
[DEDUP] 3건 중 신규 2건
[NOTIFY] Teams 전송 성공 2건 / 실패 0건
[END] 소요 시간 1.8초
```

---

## 트러블슈팅

| 증상 | 원인 / 조치 |
| --- | --- |
| `SERVICE_KEY_IS_NOT_REGISTERED_ERROR` | 공공데이터포털에서 키가 아직 활성화되지 않음. 신청 직후 1~2시간 대기 후 재시도. |
| `4xx` 에러로 즉시 실패 | 인증키 형식 오류 (Decoding 키 대신 Encoded 키를 넣었거나, 공백/줄바꿈 섞임). Secret 다시 확인. |
| 응답은 받았는데 통과 0건 | `DEBUG_DUMP=1`로 첫 응답 dump → 지역 필드명을 `filters.py`의 `REGION_FIELD_CANDIDATES`에 추가. 또는 검색 윈도우 늘려보기 (`search_window_minutes: 60`). 키워드가 너무 좁다면 `keywords_action`/`exclude_name_keywords` 완화. |
| Teams 알림이 안 옴 | (1) Workflow URL 만료 — Teams에서 재발급. (2) JSON 본문 형식이 Workflows가 기대하는 `{"text": "..."}` 가 맞는지 확인 (이 코드는 맞춰져 있음). (3) Actions 실행 로그에서 `[NOTIFY]` 라인 확인. |
| 동일 공고가 중복 알림됨 | seen.json 자동 커밋이 실패했을 가능성. Actions 실행 결과의 마지막 단계 로그 확인 — `permissions: contents: write`가 활성화되어 있어야 함. |
| GitHub Actions 한도 | 30분마다 × 720회/월 × ~5분/회 = 약 220~250분/월. 무료 한도 2,000분 안에 충분히 들어갑니다. |

---

## 파일 구조

```
narajangteo-monitor/
├── .github/workflows/monitor.yml   # cron */30 + seen.json 자동 커밋
├── src/
│   ├── __init__.py
│   ├── monitor.py                  # 메인 파이프라인 + 로깅
│   ├── nara_api.py                 # API 호출 + 재시도 + DEBUG_DUMP
│   ├── filters.py                  # 3단계 필터
│   ├── teams_notifier.py           # 웹훅 POST + Adaptive Card
│   └── dedup.py                    # seen.json 관리
├── config.yaml                     # 키워드·지역 설정
├── seen.json                       # 자동 생성·갱신 (gitignored, Actions가 강제 커밋)
├── requirements.txt
├── .gitignore
├── .env.example                    # 로컬 테스트용 템플릿
└── README.md
```

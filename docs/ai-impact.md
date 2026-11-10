# 정책도미노 · 공식 변경 사건 전체를 관리하는 LLM 영향 분석

정책도미노의 기존 **단일 수집→검증→기관업무 생성→배포** 파이프라인에 통합된 AI 분석 단계입니다. 사전에 고른 법령 1건을 시연하는 기능이 아닙니다.

## 전체 사건 수집과 분석 구분

- 수집된 **모든 변경 사건**이 AI 분석 상태 목록에 등록됩니다. 영향도 필터나 하드코딩한 법령명으로 제외하지 않습니다.
- 공식 신구 조문과 실제 담당 기관의 업무 근거가 확인된 사건에서는 **모든 검증된 기관별 검토항목**을 LLM 분석 대상으로 삼습니다.
- 공식 확인이 아직 완료되지 않았거나 기관별 검토 근거가 없는 사건은 **공식 근거 확인 대기**로 표시합니다. 이를 AI 분석 완료 또는 영향 없음이라고 간주하지 않습니다.
- LLM 입력은 공공기관의 공식 근거로 확인한 항목만 포함합니다. 상위 정책 금액을 기관 사업의 최종 선정금액으로 해석하지 않도록 `comparison_scope`를 함께 전달합니다. 민간조직을 기관별 영향 분석 범위에 넣지 않으며 LLM이 만들어 낸 새 기관/법령/URL/조치 완료 상태는 채택하지 않습니다.
- LLM 답변의 업무 영향 서술·검토 과제는 언제나 **AI 제안 초안**입니다. 원문 근거와 실제 반영 여부를 구분합니다.

## 단일 구조와 자동 갱신

```text
정기 정책 변경 수집(6시간 간격) → 공식 신구 조문 검증
    ↓
site/classic/data.json (전체 변경 사건 + 검증된 기관 업무 + 근거 지문)
    ↓
policy_domino.ai_impact (변경 사건 전체의 분석 대기열)
    ├─ 공식 근거가 없는 사건: 검증 대기
    ├─ 아직 분석하지 않은 검증 항목: LLM 분석
    └─ 근거가 동일한 기존 항목: AI 결과 재사용
    ↓
site/ai-impact/data.json (v2, 전체 사건의 진행 상황과 개별 검토 결과)
    ↓
/impact/ 와 /classic/ (사건별 완료/진행/대기 + 실제 AI 분석 카드)
    ↓
기존 GitHub Pages 단일 배포
```

- **전수 대상**: 수집된 전체 변경 사건을 관리. 실제 AI 요청은 공식 조문 검증을 통과한 기관별 검토항목에만 수행.
- **안전한 이어서 실행**: LLM이 결과를 반환할 때마다 작업 파일을 원자적으로 저장. 다음 Actions 실행에서는 남은 항목만 요청.
- **부분 변경에 대응**: 공식 근거의 사건 메타데이터·조문·업무·기관 연결을 SHA-256으로 식별. 공식 수집 시각만 바뀌어도 같은 근거라면 AI를 다시 부르지 않음. 변경된 근거 항목만 기존 AI 결과를 무효화하고 재분석.
- **호출 제한 대응**: 하나의 요청에 최대 3개 검토항목(기본값)을 묶고, 사건별로 번갈아 처리해 큰 사건 한 건이 다른 사건을 독점하지 않음.
- **무료 API 보호**: 기본 1회 최대 36개 LLM 배치 요청, 기본 배치 간 12초 간격. 무료 티어의 실제 호출 한도에 걸리면 완료 결과를 보존하고 미처리 항목을 다음 실행에 넘김. API 사용량 한도를 우회하거나 허위 분석 결과를 생성하지 않음.
- **모델 장애 대응**: Gemini 503 일시 과부하 재시도 후 같은 Gemini 서비스 안의 `PD_LLM_FALLBACK_MODEL` 대체 모델 사용. 과거 실제 성공 모델을 우선 선택할 수 있고, 결과에는 실제 응답 모델을 기록.
- **자동 운용**: 모델 키·모델명이 등록된 경우 기존 6시간 정기 수집 실행에서 대기열을 처리(Variable `PD_AI_AUTO_ENABLED=false`로 중단 가능). 특정 수동 실행 시 `analyze_ai=true`로 처리할 수도 있음. 추가 파이프라인·별도 크론 없음.

## 공공기관·사업 연결: 정부24 공식 공공서비스 원천

공식 데이터 원천: [행정안전부_대한민국 공공서비스(혜택) 정보](https://www.data.go.kr/data/15113968/openapi.do). API 명세의 `serviceList`와 `serviceDetail`을 **기존 단일 법령 수집 작업의 내부 단계**에서 실행합니다. 이 원천은 중앙부처·지자체·공공기관·교육청이 제공하는 공공서비스와 실제 운영 기준을 포함합니다.

**필수 설정:** 공공데이터포털에서 이 무료 오픈API의 활용을 신청해 인증키를 발급받고, GitHub Actions Secret **`PD_PUBLIC_SERVICE_KEY`**에 등록합니다. 기존 법제처 `LAW_OC`나 Gemini `PD_LLM_API_KEY`는 서로 다른 서비스의 키이므로 대체할 수 없습니다. 키가 없다면 공식 법령 수집·이전 81건 AI 결과는 정상 보존되지만 **새 공공서비스 기관 연결이 생성되었다고 주장하지 않습니다.**

운영 흐름:

1. 정부24 원천에서 서비스 ID, 공식 소관기관, 접수기관, 사업명, 선정기준과 상세 법령 근거를 페이지 단위로 수집합니다. 기관명·사업명을 코드에 하드코딩하지 않습니다.
2. 변경된 정책의 **실제 숫자 전후 변화**와 해당 서비스의 **같은 기준변수·비율/산식**을 대조하거나, 정확히 변경된 조항을 서비스 법령근거가 **적용한다는 명시적 인용**이 있는지 확인합니다. 제목 유사성만으로 관계를 만들어내지 않습니다.
3. 현재 V4에서 공식 법령 신구 내용이 검증된 관계는 **기관별 변경 검토사항 + AI 분석 대기열**로 연결합니다. 이전 V2 개정 지시문만 남은 관계는 **최신 법령 근거 재확인 필요**로 보이되 AI 분석 완료로 승격시키지 않습니다.
4. 공공기관이 실제로 사업·시스템을 수정했는지는 공식 조치 근거가 확보되지 않으면 확인되지 않은 상태로 유지합니다.

API 스캔 상태는 `data/public_services.json`에 증분 보존되며 마지막 페이지가 확인되기 전에는 전체 수집 완료로 표시하지 않습니다. 수정된 정부24 선정기준은 새로운 AI 근거 SHA 지문을 만들고, 변경되지 않은 법령의 기존 AI 결과는 재분석하지 않습니다. 무료 API 트래픽을 고려한 기본 실행 상한은 서비스 목록 40페이지, 상세 250건입니다. `PD_PUBLIC_SERVICE_PAGES`, `PD_PUBLIC_SERVICE_DETAILS` GitHub Variables로 조정할 수 있습니다.

**범위:** 정부24 수혜 서비스 목록을 통한 공공기관 사업 연결이므로, 정부24에 등록되지 않은 공공기관 사업·내부규정까지 완전하게 포괄한다고 주장하지 않습니다. 추후 공공기관 경영정보공개(ALIO)와 기관별 공식 공고/업무지침 등 별도 원천의 연결도 필요합니다.

## GitHub Actions 설정

기존 Secrets/Variables를 유지합니다.

| 구분 | 이름 | 의미 |
| --- | --- | --- |
| Secret | `PD_LLM_API_KEY` | Google Gemini 등 제공업체의 비공개 API 키 |
| Secret | `PD_PUBLIC_SERVICE_KEY` | 행정안전부 정부24 공공서비스 OpenAPI 인증키(무료 활용신청) |
| Variable | `PD_LLM_MODEL` | 기본 모델 ID |
| Variable | `PD_LLM_BASE_URL` | OpenAI 호환 Chat Completions API 기본 URL |
| Variable | `PD_LLM_FALLBACK_MODEL` | (선택) Gemini 503의 백업 모델 |
| Variable | `PD_AI_PREFER_FALLBACK` | (선택) Gemini 백업 모델을 우선 사용 (`true` 기본값, 기존 3.8 과부하 회피) |
| Variable | `PD_AI_AUTO_ENABLED` | (선택) `false`일 때 정기 AI 처리 중단 |
| Variable | `PD_AI_MAX_REQUESTS` | (선택) 한 실행의 최대 LLM 배치 요청 수, 기본 36 |
| Variable | `PD_AI_REQUEST_INTERVAL` | (선택) 배치 요청 간 초 간격, 기본 12 |

저장소: `dodam-heo/policy-domino`. GitHub Actions의 **Policy Domino — Official Policy Impact Pipeline → Run workflow**에서 `main`, `source=stored`, `analyze_ai=true`를 선택하면 공식 자료를 다시 수집하지 않고 기존 검증 근거의 **미분석 전체 대기열**을 처리합니다. 수동 요청 없이 정기 갱신할 때는 기존 단일 수집 워크플로가 같은 AI 단계를 실행합니다.

API 키는 브라우저와 GitHub Pages 정적 사이트에 노출하지 않습니다. Python 표준 라이브러리 `urllib`로 서버 측에서 요청합니다. Google Gemini는 전용 GenerateContent API의 구조화 JSON 스키마를 사용하며, 다른 모델 공급업체에는 OpenAI 호환 Chat Completions 프로토콜을 사용합니다. Google의 무료 API로 전송하는 내용은 **공개 법령 근거만** 포함해야 합니다. 내부기관 자료·개인정보 등을 같은 경로에 넣으면 안 됩니다.

## 로컬 실행

```bash
python -m policy_domino --source stored
export PD_LLM_API_KEY="실제 API 키"
export PD_LLM_MODEL="사용 가능한 제공업체 모델 ID"
export PD_LLM_BASE_URL="해당 제공업체의 Gemini용 /v1beta/openai 또는 다른 제공업체의 OpenAI 호환 /v1 주소"
python -m policy_domino.ai_impact --max-requests 36 --batch-size 3 --interval 12
python -m http.server 8000 --directory site
# http://localhost:8000/impact/
```

실행 결과의 `LLM_CATALOG_PROGRESS`에 전체 사건 수, 분석 가능한 사건 수, 전체 공식 검토 근거 수, 실제 AI 완료 수, 남은 대기·부분·완료 수가 표시됩니다. `site/ai-impact/data.json`은 이전 단일 사건 v1 대신 전체 사건 v2 계약으로 저장됩니다.

## 판단 경계와 검증

- 단순히 AI가 새로운 기관·규정의 존재를 주장한 것만으로 공식 영향 근거로 승격시키지 않습니다.
- 수정된 근거의 기존 AI 문구는 자동 재사용하지 않습니다. SHA-256 지문 일치를 요구합니다.
- 이전 단일 시연 결과(v1)는 공식 데이터 생성 시점과 기관·조문·출처가 정확히 일치하는 경우에만 인계할 수 있습니다. 그렇지 않으면 확인되지 않은 근거로 이전 결과를 승인하지 않고 재분석합니다.
- 추론 불가 상태에서 기존 수집·검증·배포를 중단시키거나, 분석하지 않은 사건을 분석 완료로 꾸미지 않습니다. 사용량 제한에 걸려 남은 사건은 진행/대기로 유지됩니다.
- 자동 테스트: `python -m unittest discover -s tests -p 'test_*.py' -v`, `node site/ai-impact/test_ui.cjs`, `python -m policy_domino.audit`.

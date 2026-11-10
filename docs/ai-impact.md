# 실제 LLM을 이용한 공공기관별 업무 영향 분석

이 기능은 **단순히 AI로 코드를 작성한 결과가 아니라**, 등록된 실제 LLM에 공식 변경 전후 조문을 보내고 정책의 실무 영향을 분석한 답을 받는 기능입니다.

## 실제 동작

```text
공식 법령·행정규칙 데이터 (기존 수집 엔진)
  → 현재 검증된 기관별 변경 근거 (행정조직·조문·신구 원문)
  → 외부 또는 로컬 OpenAI-compatible LLM API 실호출
  → AI가 기관별 업무 영향과 검토 조치를 JSON으로 제안
  → 기관/조문/근거 ID 일치 여부와 내용 크기 검증
  → site/ai-impact/data.json (별도 데이터, AI 초안임을 명시)
  → /impact/ 의 해당 사건에만 AI 분석 카드 표시
```

**AI는 공식 출처를 대신하지 않습니다.** 검증된 현재 사건의 `v4_verified_source` 기관 검토항목만 입력으로 보냅니다. 이전 V2 잠정 근거나 단순 기관명 언급은 입력하지 않습니다. 모델이 새로운 기관명·조문·URL·반영 상태를 제시하더라도 이를 신뢰하지 않고 소스 데이터의 식별자와 매칭한 내용만 보여 줍니다. 업무 영향 서술 자체는 AI 검토 초안이므로 담당자가 최종 확인해야 합니다. **AI로 기관의 실제 조치 완료를 판정하지 않습니다.**

## 필요한 설정

Python 3.12 이상. 별도 Python 패키지 설치 없이 표준 라이브러리 `urllib`만 사용합니다. 인터넷이 필요합니다(로컬 LLM을 사용할 경우 로컬 OpenAI 호환 서버). LLM 계정·모델은 사용자가 직접 제공해야 합니다.

| 환경변수 | 설정 |
| --- | --- |
| `PD_LLM_API_KEY` | 비밀 인증키. CLI 인자로 입력하거나 소스에 저장하지 않음 |
| `PD_LLM_MODEL` | 제공업체의 실제 모델 ID. 비어 있으면 추론 시작 불가 |
| `PD_LLM_BASE_URL` | OpenAI 호환 API의 `/v1` 기본 주소. 미설정 시 `https://api.openai.com/v1` |

호출 방식은 `POST {base_url}/chat/completions` 및 JSON `messages`입니다. 이 **API와 호환되는 모델**에 한해 제공업체를 교체할 수 있습니다. 인터넷 모델은 HTTPS만 허용하고 로컬 호스트에서는 HTTP 연결도 가능합니다. 모든 LLM을 무조건 지원한다는 뜻은 아닙니다.

## 실행 및 시연

```bash
# 1. 이미 수집된 공식 근거로 자료 재생성
python -m policy_domino --source stored

# 2. 아래 값은 사용할 모델 제공업체의 값으로 설정
export PD_LLM_API_KEY="YOUR_PRIVATE_API_KEY"
export PD_LLM_MODEL="YOUR_PROVIDER_MODEL_ID"
export PD_LLM_BASE_URL="https://api.openai.com/v1"

# 3. 실제 모델 1회 호출 → 공식 근거와 연계된 기관 검토 초안 생성
python -m policy_domino.ai_impact --limit 3

# 4. 별도 터미널에서 웹사이트를 실행해 결과 보기
python -m http.server 8000 --directory site
# 브라우저에서 http://localhost:8000/impact/
```

모델은 검증된 고영향 사건 중 기관 검토 근거가 있는 사건 하나를 자동으로 선택합니다. 특정 사건을 선택하려면 `--event-id 'v4:...'`를 사용합니다. 한 번에 보내는 검토항목은 1–5개로 제한합니다. 결과가 생성되면 정확히 해당 사건의 AI 카드만 표시됩니다.

GitHub Actions에서는 저장소 **Settings → Secrets and variables → Actions**에 Secret `PD_LLM_API_KEY`, Variable `PD_LLM_MODEL` (선택: `PD_LLM_BASE_URL`)를 설정하세요. **Policy Domino — Official Policy Impact Pipeline → Run workflow**에서 `source=stored`, `analyze_ai=true`를 선택하면 같은 배포 워크플로 안에서 실제 추론과 사이트 배포가 실행됩니다. 정기 실행은 추가 LLM 비용이 발생하지 않도록 AI를 자동 호출하지 않습니다.

## 오류와 제한

- 인증값이나 모델 ID가 없으면 **실제 분석을 실행하지 않고 오류로 중단**합니다. 미리 작성한 가짜 AI 결과를 표시하지 않습니다.
- 제공업체가 통신 실패·비정상 JSON·미확인 기관 ID·다른 근거 인용을 반환하면 새 결과 파일을 발행하지 않습니다.
- Gemini 등 제공업체가 **HTTP 503(일시적 과부하)** 또는 일시적 500/502/504 오류를 반환하면 3초, 9초 간격으로 **최대 2회 자동 재시도**합니다. 여전히 실패하면 실제 AI 분석 결과를 발행하지 않습니다. 404(모델 ID), 401/403(인증), 429(요금제·할당량)는 무분별하게 재시도하지 않습니다.
- 공식 데이터가 새로 생성되면 이전 LLM 결과와 `source_generated_at`이 달라져 웹 화면에서 표시되지 않습니다. 새 자료에 맞춰 다시 호출해야 합니다.
- 공개 GitHub Pages는 정적 화면입니다. **브라우저에서 비밀 API 키로 직접 모델을 호출하지 않습니다.** 추론은 로컬 CLI 또는 GitHub Actions 서버에서 수행하고, 검증된 출력만 정적 데이터로 제공됩니다.
- 공개된 법령 변경 근거만 LLM에 전송합니다. 개인정보·내부 업무 자료를 이 경로에 넣지 마세요.
- LLM이 실제로 어떤 제도·기관에 영향을 주는지 탐색할 수 있는 범위는 **현재 수집·검증된 조문과 기관 연결 근거에 한정**됩니다. LH·SH·한국장학재단 등의 파급관계 탐색을 자동으로 완성한 것은 아닙니다.

## 자동 테스트

```bash
python -m unittest tests.test_ai_impact -v
node site/ai-impact/test_ui.cjs
```

모의 HTTP 응답을 이용해 실제 모델 API 요청 형식과 입력 증빙이 올바른지 확인하며, 공급업체의 응답을 조작한 가짜 기관·다른 출처·중복 결과를 거부하는 테스트를 포함합니다. **모의 테스트 통과는 외부 유료 모델에 대한 실제 호출 성공과 다릅니다.** 실제 호출은 위의 환경변수를 설정하고 추론 명령이 성공해야 검증됩니다.

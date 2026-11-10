# 정책도미노 | Policy Domino

공식 정책 변경이 어떤 공공기관의 제도·사업·업무에 파급되는지 **공식 근거와 함께** 보여주는 AI 활용 서비스.

서비스: https://dodam-heo.github.io/policy-domino/impact/

## 단일 운영 구조

```
공식 법령·행정규칙·자치법규 변경 탐색 (국가법령정보 API)
  → 동일 법령의 구·신 조문 검증 / 연도별 고시 후속 기준 비교
  → 변경 조항을 직접 적용하는 공공규정 확인
  → 정부24 등 공식 서비스 운영기준과 교차 대조
  → 실제 연결된 공공기관·사업·업무 검토사항 생성
  → 실 LLM 검토 의견 (공식 사실을 덮어쓰지 않음)
  → 하나의 데이터 계약·하나의 화면 템플릿
```

운영 진입점은 `python -m policy_domino` 하나입니다. `--source official`은 공식 API에서 신규 변경을 수집하고, `--source stored`는 **저장된 공식 원문 증거**로 동일 파이프라인을 재실행합니다. 이전 개발 버전의 분석 카드나 가공된 영향 데이터는 현재 산출물의 입력으로 사용하지 않습니다.

- `policy_domino/engine/pipeline.py`: 공식 변경 자료 수집·비교·근거 저장
- `policy_domino/engine/publication.py`: 검증된 정책 사건·기관별 조치의 단일 생성기
- `policy_domino/public_services.py`: 실제 공공서비스 선정기준과 정책의 적용 관계
- `policy_domino/ai_impact.py`: 모델별 접속을 분리한 근거 제약 LLM 분석
- `site/templates/agency.html` + `site/assets/`: 한 화면의 상세 UI

**숫자 해석 원칙:** 상위 정책 기준액의 변경과 실제 기관 사업의 선정·지급금액 변경은 다릅니다. 사업별 대상, 적용비율, 산식, 반올림 기준의 독립 검증 없이는 상위 변경값을 사업 금액으로 표시하지 않습니다.

정책 상세의 순서는 **발령기관·정책명 → 실제 변경내용 및 신구 비교 → 관련 법령 → 영향을 받는 기관·사업 → 검토할 조치**입니다. 민간조직은 영향 분석 범위에 포함하지 않습니다.

## 검증·실행

Python 3.12+ / Node.js 22+.

```bash
python -m policy_domino.audit
python -m policy_domino --source stored
python -m unittest discover -s tests -p 'test_*.py' -v
node site/classic/test_ui.cjs
node site/v4/test_ui.cjs
node site/ai-impact/test_ui.cjs
```

GitHub Actions 단일 정기 파이프라인이 공식 수집·검증·결과 저장·GitHub Pages 배포를 담당합니다. 법제처 공개 DRF 호출 식별자 `LAW_OC`의 기본값은 요청에 따라 코드에 `dori`로 지정했습니다. `PD_PUBLIC_SERVICE_KEY`와 LLM의 비공개 인증키는 Secrets/Variables로 관리합니다.

상세 데이터 계약, 제출 범위와 한계: [아키텍처](docs/architecture.md). AI 설정: [AI 분석](docs/ai-impact.md).

## 공식 수집·누적 저장 및 누락 감지

기관명·급여명·분야명을 등록하지 않습니다. 법제처 공식 API의 법령(`law`), 행정규칙(`admrul`: 훈령·예규·고시·공고·지침 등), 자치법규(`ordin`)를 **발령일자 구간 전체**로 탐색합니다. 법령 변경이력도 별도 날짜 인덱스로 확인합니다.

- **공식 목록 발견:** 문서 ID·버전·발령기관·일자와 원문 링크를 `data/v4_state.json`에 보존하고, 본문 분석 전이라도 화면의 전체 목록에 ‘본문 대조 대기’로 표시합니다.
- **상세 추출:** 문서별 신구 조문·별표·첨부자료를 확인합니다. 공식 PDF와 HWPX에서 읽을 수 있는 텍스트는 대조 자료로 보존하며, 읽을 수 없는 HWP·이미지형 첨부는 공식 링크와 함께 미확인 상태로 유지합니다.
- **과거 범위:** 기본 최근 10년을 28일 구간으로 순환 스캔하며, 각 회차 6구간을 수집합니다. 최근 8일의 법령·행정규칙·자치법규 전체 목록을 별도 중첩 조회하고, 실패한 날짜·현행·연혁 구간을 재시도합니다. 모든 수집 결과를 날짜별로 기록합니다. 수집된 공식 자료를 이전 버전의 분석 결과로 대체하지 않습니다.
- **무손실 재실행:** 새 기록이 없거나 일부 API 오류가 발생해도 기존 공식 기록을 유지하며, 파일은 임시 파일에서 원자적으로 교체합니다. 모든 공식 수집 호출에 실패하면 신규 수집 성공으로 표시하지 않고 실패 기록을 저장합니다.
- **범위와 한계:** ‘공식 목록 등록’, ‘원문 비교 완료’, ‘공공기관 영향 확인’은 각각 다른 상태입니다. 전체 법령과 모든 공공기관의 영향 분석이 이미 완료됐다고 주장하지 않습니다.

`LAW_OC`는 DRF 호출 식별자로 `dori`를 기본 사용하므로 Secret을 별도로 등록할 필요가 없습니다. Actions의 `official` 모드는 신규 공식 정책을 수집하고 누적 저장하지만 `stored` 모드는 과거에 저장한 공식 근거만 재분석합니다. 별도의 LLM 키와 서비스 API 키는 노출하지 않습니다.

조정 변수: `PD_HISTORY_DAYS`, `PD_BACKFILL_WINDOWS_PER_RUN`, `PD_BACKFILL_WINDOW_DAYS`, `PD_RETRY_WINDOWS_PER_RUN`, `PD_V4_DETAILS`, `PD_FETCH_OFFICIAL_ATTACHMENTS`. 재생성만 할 때는 `python -m policy_domino --source stored`, 실제 수집·저장은 `python -m policy_domino --source official`입니다.

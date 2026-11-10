# 정책도미노 기술 설계

## 목적·범위

공식 법령·시행령·시행규칙·고시·훈령·예규 등의 변경 사건을 탐지하고, 변경 사실로부터 관련 공공기관의 담당 업무와 연계되는 지점을 **검증된 공개 근거**로 추적한다. 특정 기관이나 정책명을 하드코딩하여 결과를 꾸미지 않는다. 민간조직은 기관별 영향 분석 범위에 포함하지 않는다.

## 단일 운영 파이프라인

```text
GitHub Actions: policy-domino.yml
       ↓
python -m policy_domino --source official
       ↓
official_api / engine.collect_index
       ↓
engine.pipeline / engine.events
       ↓
engine.relationships / engine.official_links / engine.dependents
       ↓
site/v4/data.json             (공식 원천 근거 · 부분 수집 상태)
       ↓
engine.classic_bridge
  ├─ engine.agency_actions    (변경된 공식 조문 → 업무)
  ├─ engine.impact_scope      (기관·연계규정 파급 범위)
  └─ engine.legacy_recheck    (별도 역사자료: 재검증 대기)
       ↓
site/classic/data.json        (공통 화면 데이터 계약)
       ↓
engine.classic_pages          (단일 템플릿에서 두 경로 생성)
       ↓
site/impact/index.html / site/classic/index.html
       ↓
단일 GitHub Pages 배포
```

`--source stored`는 새로운 API 호출 없이 저장된 공식 출처와 증빙으로부터 같은 하위 단계를 재생성한다. 이는 UI 변경 시 근거를 다시 수집하지 않고도 테스트할 수 있는 경로다. 정기 수집·사이트 배포는 별도 워크플로가 없다. CI 검사 전용 워크플로에는 배포 권한이 없다.

## 데이터 계약과 검증 상태

**공식 인덱스 기록**과 **본문 확보**, **변경된 조문 검증**, **다른 규정의 적용 관계**, **기관별 검토 업무**는 서로 다른 상태다. 전 단계의 존재만으로 다음 단계의 확인을 가정하지 않는다.

- `site/v4/data.json` : 공식 인덱스·개정 사건·실제 비교 조문·증명된 연계·수집 미완료 수량
- `site/classic/data.json` : `policy-domino-next-v1` 계약. `events` 변경 사건과 `actions` 기관별 업무 검토 항목을 독립적으로 담는다.
- `evidence_scope=v4_verified_source` : 공식 신구 조문을 직접 확인한 근거.
- `evidence_scope=legacy_official_directive_awaiting_recheck` : 과거 V2 공식 개정 지시문의 이전·이후 값으로 확인했지만 최신 재검증이 필요한 항목.
- `status`는 실제 기관별 처리 완료 여부의 객관적 기록 없이 `조치 확인` 또는 `미조치 확인`으로 채우지 않는다.

'영향도 큼'은 같은 사건에서 근거가 확인된 서로 다른 직접 검토 기관 2곳 이상 또는 변경 조항을 적용하는 독립 규정 관계 2건 이상이다. 동일 조문·기관을 반복 세지 않는다. 기관명 등장·상위법 존재만으로 자동 확장하지 않는다.

## 보존·이력

과거 단독 수집 `watch.py`, `impact_scanner.py`, 이전 `v2/v3/next` 구현과 복수의 GitHub Pages 워크플로는 모두 [변경 전 보관 브랜치](https://github.com/dodam-heo/policy-domino/tree/archive/pre-canonical-pipeline-20261110)에 남겨 두었다. 새 `main`의 운영 코드는 `policy_domino`에 집중한다.

기존 `data/v2_state.json` 및 `site/classic/legacy_source.json`은 **이전 근거·수집 인덱스** 호환을 위해 남길 수 있으나 실행 엔진은 아니다. `engine.pipeline.bootstrap_old_index`는 새 공식 V4 증빙이 초기화될 때 이력 메타데이터만 후보로 사용하며, 과거 V2 기관별 조치 추론은 현재 공식 검증으로 승격시키지 않는다.

## 테스트·배포 안전장치

- `python -m policy_domino.audit`: 단일 정기 워크플로, 단일 Pages 배포자, 루트 구식 감시 스크립트/레거시 import 부재
- `python -m unittest discover -s tests -p 'test_*.py' -v`: API 응답 파싱, 조문 비교, 연계 관계, 기관 업무 추출, 영향 범위 및 완료 상태 오판 방지
- `node site/classic/test_ui.cjs`: 기본 영향도 필터, 동일 UI 템플릿/데이터 원천, 화면 호환성
- `node site/v4/test_ui.cjs`, `node site/test_adapter.cjs`: 공식 데이터와 브라우저 표시 계약
- GitHub Actions: 수집→테스트→검증된 생성물만 `main`에 저장→하나의 Pages 아티팩트로 배포
- 실패 시 이전 공개 사이트를 유지하고, 새 오류를 성공이나 '영향 없음'으로 표시하지 않는다.

## 후속 분석 범위

LH·SH·한국장학재단 같은 집행기관의 파급 범위 확장은 조문 단위 종속 관계, 기관별 공식 업무 규정 및 변경 전·후 운영 기준 확인을 필요로 한다. 기관명 사전을 늘리는 것만으로 해결하지 않는다. 지금은 **코드 구조와 단일 운영 경로 정비**에 초점을 맞춘 단계다.

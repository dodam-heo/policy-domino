# 정책도미노 · Policy Domino

**법령·행정규칙의 확정된 변경을 공공기관의 구체적 검토 업무까지 추적하는 근거 기반 소프트웨어**

서비스: https://dodam-heo.github.io/policy-domino/impact/

정책도미노는 변경된 법령을 다시 고치라고 지시하는 서비스가 아닙니다. **공식 변경 내용 → 실제 관련 규정 → 담당 공공기관 → 검토해야 할 업무**를 공개 근거와 함께 제공하는 것이 목적입니다.

수집 대상은 특정 산업이나 기관을 미리 선정하지 않은 법령·행정규칙 전체 범위입니다. LH, SH, 한국장학재단 같은 공공기관의 파급 영향은 기관명만 언급되었다는 이유로 확정하지 않고, 해당 변경 조항과 집행 업무의 관계가 확인될 때만 표시합니다. 미확인 관계는 검토 후보로 분리합니다.

## 프로젝트 구조

```text
policy_domino/
  __main__.py             단일 운영 진입점
  official_api.py          국가법령정보 공식 API 통신·원문 추출
  semantic_diff.py         원문 신구 문장 비교
  audit.py                 중복 파이프라인·오래된 코드 재유입 방지
  engine/
    pipeline.py            공식 변경 사건 수집·증빙 데이터 생성
    collect_index.py       공식 변경목록/연혁 인덱스
    events.py              개정 사건과 이전 버전 비교
    relationships.py       변경된 조문과 연계 규정 검증
    official_links.py      법제처 위임 규정 연결
    dependents.py          후속 규정 확인
    agency_actions.py      공공기관 업무 검토사항 구성
    impact_scope.py        '영향도 큼' 판정
    legacy_recheck.py      이전 근거를 재검증 대기 상태로 격리
    classic_bridge.py      화면 데이터의 단일 생성기
    classic_pages.py       두 화면 경로의 정적 파일 생성
    stage_refresh.py       저장된 공식 근거로 재생성
tests/                    수집·분석·증빙·UI 계약 자동 테스트
site/
  templates/agency.html   하나의 공통 화면 템플릿
  assets/                 공통 CSS·JavaScript
  impact/                 기본 '영향도 큼' 화면
  classic/                동일 데이터의 호환 접근 경로
  v4/                     원문 검증 현황 조회용 공개 경로
data/                     진행 상태와 출처 증빙 스냅샷
.github/workflows/
  policy-domino.yml       유일한 정기 수집 및 GitHub Pages 배포
  refactor-quality.yml    테스트만 실행 (배포 권한 없음)
docs/architecture.md     데이터 모델·판정 원칙·운영 경계
```

**운영 경로는 하나뿐입니다.** `policy_domino/__main__.py`가 증빙 수집·갱신을 호출한 후 기관 영향 데이터와 화면을 생성합니다. 과거 `v2/`, `v3/`, `v4/`, `next/`, `watch.py`, `impact_scanner.py` 기반의 중복 실행 코드는 생산 브랜치에서 제외했고, 삭제 전 상태는 [기록 보관 브랜치](https://github.com/dodam-heo/policy-domino/tree/archive/pre-canonical-pipeline-20261110)에 보존했습니다. **데이터 형식 이름의 V2/V4는 검증 출처·스키마의 버전이며 별도 실행 파이프라인이 아닙니다.**

## 실행·검증

Python 3.12+ 및 Node.js 22+.

```bash
# 테스트와 아키텍처 검사 (인터넷·API 인증 불필요)
python -m policy_domino.audit
python -m unittest discover -s tests -p 'test_*.py' -v
node site/v4/test_ui.cjs
node site/classic/test_ui.cjs
node site/test_adapter.cjs

# 수집된 공식 근거를 다시 분석하여 화면 생성
python -m policy_domino --source stored

# 법제처 API에서 새 변경사항을 수집하고 화면 생성
LAW_OC="<공식 API 인증값>" python -m policy_domino --source official
```

GitHub Actions는 **`.github/workflows/policy-domino.yml`** 하나만 정기 실행합니다. 6시간마다 공식 수집→검증→기관별 분석→배포를 수행합니다. `main` 코드가 바뀌면 기존 공식 증빙으로 재생성·배포하며, 수동 실행 때는 두 모드 중 선택할 수 있습니다. `LAW_OC`는 GitHub Actions Secret 또는 Variable로 설정하며, 인증값을 소스에 넣지 않습니다. 검증 실패·API 실패 시 배포는 중단됩니다.

## 결과 해석

- **'영향도 큼' 기본 선택**: 공식 근거가 있는 직접 검토 기관 2곳 이상 **또는** 변경된 조항을 실제 적용하는 규정 2건 이상인 사건. 정책의 사회적 중요도 등급이 아닙니다.
- **현재 공식 신구 본문**: 확인한 조문과 이전·변경 내용을 보여줍니다.
- **이전 자료 · 재검증 대기**: 이전 V2 공식 개정 지시문으로 확인했던 항목입니다. 최신 검증 결과로 둔갑시키지 않습니다.
- **업무 검토 필요**: 실제 기관 시스템의 변경 완료·미조치를 확정했다는 뜻이 아닙니다.

프로젝트의 설계 결정, 데이터 계약, 증빙 검증 기준 및 남은 기능 범위는 [기술 설계](docs/architecture.md)에 기록했습니다.

## 알려진 한계

전국 모든 공공기관의 내부 업무 시스템에는 접근하지 않습니다. 따라서 LH·SH·한국장학재단 등의 업무 영향도 법령·관련 규정과 집행 근거가 확보된 범위에서만 도출됩니다. 모든 기관·규정의 전수 연결이 완성된 상태라고 주장하지 않습니다.

# 정책도미노 | 공식 정책 변경 → 공공기관별 업무 영향

공개: https://dodam-heo.github.io/policy-domino/impact/

정책도미노는 법률·시행령·시행규칙·행정규칙의 공식 변경을 추적하고, **어느 공공기관의 어떤 검토 업무로 이어지는지**를 근거와 함께 보여주는 프로젝트입니다. 법령을 다시 고치라는 순환 지시를 만들거나, 증거 없이 기관 조치의 완료 여부를 판단하지 않습니다.

## 현재 데이터와 화면

- `/impact/`: 기본 '영향도 큼' 필터가 적용된 신규·개정 변경 목록과 기관별 영향 분석.
- `/classic/`: 동일한 변경/검토 데이터를 사용하는 별도 접근 경로.
- `/v4/`: 공식 원문 수집·검증 진행 상태 및 연계 탐색.
- `/previous.html`: 예전 화면 참고용.
- `site/classic/data.json`: V4 공식 신구 본문에 근거한 분석과 이전 V2 공식 개정 지시문 기반 항목을 **서로 다른 검증 상태**로 제공.

분류 '영향도 큼'은 검증된 직접 검토 기관 2곳 이상 또는 실제 변경 조항이 적용되는 규정 2건 이상이다. 이전 V2 근거는 최신 재검증 대기 표시를 유지한다. 수집 공백과 미확인 항목을 '영향 없음'으로 단정하지 않는다.

## 설계와 코드

[기술 설계·품질 기준](docs/architecture.md) 참고.

| 책임 | 구현 |
| --- | --- |
| 공식 자료 수집·비교 | `v2/collector.py` |
| 공식 원문 근거/연계 탐색 | `v4/pipeline.py` |
| 기관별 검토 화면용 데이터 | `v4/classic_bridge.py` |
| 증빙에 따른 영향 범위 | `v4/impact_scope.py` |
| 단일 화면 템플릿 생성 | `v4/classic_pages.py`, `site/templates/agency.html` |
| 공유 프론트엔드 | `site/assets/classic.css`, `site/assets/classic.js`, `site/assets/impact-model.js` |
| 검증과 배포 | `.github/workflows/classic-publish.yml` |

## 개발 검증

```bash
python -m unittest v4.test_impact_scope v4.test_classic_pages -v
node site/classic/test_ui.cjs
node site/test_adapter.cjs
```

화면만 재생성하려면 `python -m v4.classic_pages`, 공식 검증 자료로 기관별 검토 데이터를 재작성하려면 `python -m v4.classic_bridge`. GitHub Actions에서 법제처 API용 `LAW_OC`를 Secret 또는 Variable로 설정한다. 인증값을 코드에 저장하지 않는다.

## 알려진 한계

기관별 업무 연계는 공식 근거가 검증된 범위만 제공하며 LH·SH·한국장학재단 등 여러 집행기관 전체를 자동 추적하는 기능은 아직 완성되지 않았다. 전국 공공기관에 대한 전수 판정이나 실제 내부 시스템의 반영 완료를 보장하지 않는다. 전체 수집 파이프라인과 데이터 계약 구조는 추가 개선 대상이다.

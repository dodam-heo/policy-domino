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

GitHub Actions 단일 정기 파이프라인이 공식 수집·검증·결과 저장·GitHub Pages 배포를 담당합니다. `LAW_OC`, `PD_PUBLIC_SERVICE_KEY` 및 LLM 설정은 Secrets/Variables로 제공하며 코드에 포함하지 않습니다.

상세 데이터 계약, 제출 범위와 한계: [아키텍처](docs/architecture.md). AI 설정: [AI 분석](docs/ai-impact.md).

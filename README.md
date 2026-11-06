# POLICY DOMINO · 자동 정책 변경 감시

공식 정책 게시정보를 GitHub 클라우드에서 자동으로 가져오고 GitHub Pages로 열람하는 **시범판**입니다. 사용자 PC에서 Python 또는 서버 실행은 필요하지 않습니다.

## 작동 방식
- GitHub Actions가 매시간 23분(UTC)에 실행됩니다. 실행 시각은 지연될 수 있습니다.
- 중소벤처기업부 공식 RSS 5종을 수집하고 이전 실행 데이터와 비교해 신규/수정 게시를 감지합니다.
- 변경 관련 표현이 포함된 게시물을 **변경 후보**로 표시하고 원문 링크를 제공합니다.
- 첫 실행은 기준선 설정이므로 신규 정책 확정이나 타 기관 조치 의무를 의미하지 않습니다.

## 웹사이트
Pages 설정에서 Source를 **GitHub Actions**로 선택한 후, [Actions → Policy Domino - Auto Watch and Pages](https://github.com/dodam-heo/policy-domino/actions/workflows/auto-watch.yml)에서 최초 실행 결과를 확인하세요.

배포 완료 후 예상 주소: https://dodam-heo.github.io/policy-domino/

## 중요한 기능 제한
현재의 기능은 공개 RSS 자동 감시이며, 전국 모든 기관의 정책 변경을 포괄하거나 기관 홈페이지·첨부 게시물의 정확한 수정 위치를 자동 판정하는 범용 기능은 구현되지 않았습니다.
공개 저장소이므로 비공개 문서나 API 키를 파일에 저장하지 마세요.

문제가 생기면 Actions 실행 로그의 실패 단계를 먼저 확인하세요. 특히 GitHub Pages Source가 GitHub Actions로 지정되지 않으면 배포 단계에서 실패할 수 있습니다.

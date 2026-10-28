# 공급자 설정과 검색 조건

## Google: 기본 발견 경로

최근 30일의 Google 검색 링크를 생성합니다. 날짜는 실행 시 Asia/Seoul 기준으로 계산해 `after:YYYY-MM-DD before:YYYY-MM-DD`를 질의에 넣습니다. 다음날을 상한으로 지정해 오늘도 포함합니다. 실제 결과 화면에서 적용된 기간을 확인하세요. 검색된 날짜가 채용 시작일·마감일을 증명하지 않으며, PDF의 날짜 인식·색인 지연·사이트별 검색 노출 차이 때문에 누락이 가능합니다. 최근 한 달 질의와 별개로 관심 회사의 진행 중 목록을 유지하세요.

Google 결과 페이지를 자동 크롤링하지 않습니다. API 키가 필요 없는 링크 생성입니다. 연결된 AI의 허용된 검색 도구를 사용하는 경우 그 도구의 이용 조건·가용성에 따릅니다. 검색 결과 요약을 모집 조건의 최종 근거로 쓰지 마세요.

2026-10-27 확인한 [Google Custom Search JSON API 안내](https://developers.google.com/custom-search/v1/overview)는 신규 이용자 신청 종료, 기존 고객 2027-01-01 이전 전환을 명시합니다. 따라서 이 서비스를 신규 사용자용 필수 의존성으로 구현하지 않았습니다. [Google 기간 필터 안내](https://support.google.com/websearch/answer/142143?hl=en).

## 사람인: 키 없이 시작하기

기본적으로 `get_saramin_search_links` 또는 `python -m jobmonitor.cli saramin-links --query "관심 직무"`로 공개 검색과 최근 기간 Google 사이트 검색 링크를 이용합니다. 키·로그인·유료 API가 필요하지 않습니다. 링크를 생성할 뿐 검색 결과를 크롤링하거나 DB에 자동 저장하지 않습니다. `run`은 키가 없으면 이 경로로 진행하고 discovery_only 상태로 수집 범위를 명확히 알립니다.

### 선택 기능: 공식 API 자동 수집

1. [이용신청](https://oapi.saramin.co.kr/join)에서 본인 이메일 인증·이름·회사/학교·전공/부서·전화·실제 사용 URL을 입력합니다.
2. 50자 이상으로 개인 구직 목적과 로컬 저장 방식을 설명합니다. 허위 조직·URL을 입력하지 말고 로컬 도구 URL 기재가 불명확하면 `api@saramin.co.kr`로 문의합니다.
3. 본인이 약관·개인정보 동의와 신청을 완료하고 승인을 기다립니다.
4. 승인 후 로그인 → Application → 앱 등록 → 내 앱리스트 → 앱에서 access-key를 확인합니다.
5. `.env`의 `SARAMIN_ACCESS_KEY`에 입력합니다.

[사용안내](https://oapi.saramin.co.kr/guide/info)는 하루 500회, [주의사항](https://oapi.saramin.co.kr/caution)은 500건으로 표현하므로 승인 시 적용 단위도 확인하세요. 도구의 기본 로컬 호출 예산은 100회/일이며 실패·재시도도 포함합니다. 다른 프로그램과 같은 키를 쓰는 서버 집계량은 별도입니다. [명세](https://oapi.saramin.co.kr/guide/job-search)의 0 기반 페이지 번호·110개 최대 응답·경력 코드·close-type을 반영합니다. 상세 JD 전체를 제공한다고 가정하지 않습니다. [키 발급 절차](https://oapi.saramin.co.kr/guide/1).

## 네이버: 선택 기능

신규 신청은 [NAVER API HUB](https://guide.ncloud-docs.com/docs/apihub-application) 경로입니다.

1. 네이버 클라우드 콘솔 → All Services → Application Services → NAVER API HUB.
2. Subscription에서 실제 적용 약관·개인정보·요금 조건을 확인하고 본인이 신청합니다.
3. Application 등록 → NAVER 검색/블로그 선택 → 영문/숫자/하이픈 20자 이내 앱 이름을 입력합니다.
4. 해당 앱 → API 관리/인증 정보에서 Client ID와 Client Secret을 확인합니다. NCP IAM access key와 다릅니다.
5. `.env`에서 `NAVER_MODE=hub`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 설정합니다. 콘솔 이용 한도·요금 알림을 확인합니다.

[HUB 명세](https://api.ncloud-docs.com/docs/naver-api-hub-search-blog)는 일 25,000회, display 최대 100, start 최대 1000을 안내합니다. 로컬 예산은 하루 100회입니다. 기존 Developers 승인 키만 `NAVER_MODE=legacy`를 사용하세요. [이전 공지](https://developers.naver.com/notice/article/32973), [인증](https://api.ncloud-docs.com/docs/naver-api-hub-overview), [요금 개요](https://guide.ncloud-docs.com/docs/apihub-overview).

[검색 API 약관](https://developers.naver.com/products/intro/terms/terms.md)의 저장·가공·AI 활용 제한을 반영해 결과를 사용자 화면에만 일시 표시하고, MCP·AI·SQLite·점수화에 보내지 않습니다. HUB 가입 시 적용 계약도 확인하세요. 검색 결과를 자동으로 원문 추적하는 기능은 없습니다.

## 플랫폼과 회사 원문

[잡코리아 제휴 API](https://www.jobkorea.co.kr/network/Popup_Xml.asp)는 개인 사용 등을 신청 대상에서 제외합니다. [자소설 약관](https://jasoseol.com/terms)은 무허가 자동 수집을 금지합니다. 캐치의 개인용 공식 검색 API는 이번 조사에서 확인하지 못했습니다. 이들 사이트는 수동 발견·허용 회사 원문 등록 경로입니다.

공개 페이지라고 자동 수집·저장이 모두 허용되는 것은 아닙니다. 회사별 약관·허락 근거를 sources.json에 기록하고 robots 검사도 통과해야 합니다. 로그인·CAPTCHA·사설 API 우회는 하지 않습니다.

## 공개 커넥터 검토

[saramin-job-search](https://github.com/USER-IS-THE-NAME/saramin-job-search), [PyNaver](https://github.com/WooilJeong/PyNaver), [py-mcp-naver](https://github.com/pfldy2850/py-mcp-naver)의 공개 README와 MIT 라이선스를 검토했습니다. 신규 인증·현재 약관·이 파이프라인 요구를 보장하지 않아 코드 복사나 필수 의존성 추가 없이 작은 자체 어댑터를 구현했습니다. 이 비교는 보안 감사나 실동작 보장이 아닙니다.

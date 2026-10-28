# Korean Career Discovery MCP

사용자가 원하는 직무·산업을 말하면 AI가 인접 직무와 검색어를 제안하고, 대화로 범위를 정한 뒤 한국 채용 공고를 확인하는 Python 파이프라인·표준 stdio MCP·선택형 대화 스킬입니다. 특정 전공·경력·산업을 기본값으로 가정하지 않습니다.

**Google 최근 30일 검색을 기본 발견 경로로 사용합니다.** 검색 링크를 만들 뿐 Google 검색결과를 크롤링하는 도구는 아닙니다. 회사 원문·공식 API로 모집 조건과 마감일을 확인합니다. 검색 페이지 날짜는 공고의 실제 접수기간과 다르며, 오래전에 올라온 상시·진행 중 공고는 최근 30일 필터에서 빠질 수 있습니다.

## 대화로 범위 정하기

1. 사용자가 관심을 자유롭게 말합니다. 예: “매장 운영 개선”, “여행 서비스 기획”.
2. AI가 실제 업무 중심으로 직접·인접·탐색 직무를 제안하고 연결 이유를 설명합니다.
3. 이미 알려진 사실을 재질문하지 않고, 검색에 영향을 주는 질문을 한 번에 1–3개 묻습니다. 모름·제외·다른 답도 허용합니다.
4. AI의 제안과 사용자가 받아들인 범위를 분리합니다. 초안에는 가설을 남기고, 선택한 범위만 확정 프로필로 저장합니다.
5. 확정 프로필의 직무·산업·검색어로 질의를 만들고, 결과를 보고 범위를 다시 조정합니다.

대화와 확장 추론은 연결된 호스트 AI가 MCP 서버의 대화 지침 또는 선택형 스킬 지침에 따라 수행합니다. MCP 자체가 LLM을 내장하거나 자동으로 사용자의 진로를 판정하는 것은 아닙니다. 추가 AI API 키도 필요하지 않습니다. [대화 설계와 프로필](docs/INTAKE.md).

## 기능과 범위

| 기능 | 구현 |
|---|---|
| Google 발견 | 최근 30일 검색 링크, 회사/채용사이트/PDF 질의; API 키 불필요 |
| 사람인 | 키 없이 공개 검색·최근 기간 Google 사이트 검색 링크. 공식 API 자동 수집은 키가 있을 때만 선택 제공 |
| 회사 원문 | 이용 근거를 등록한 공개 페이지·첨부, robots 검사 |
| 문서 | 텍스트 PDF, 선택 한국어/영어 OCR, HWPX, 선택 hwp5txt |
| 저장·판정 | SQLite 이력, 설명 가능한 적합도 점수, 신입/경력 구분, 중복·변경·3일 내 마감 |
| 네이버 | 선택 HUB/legacy API의 사용자용 일시 검색 화면. 결과의 AI/DB 전달 제외 |
| 스킬·MCP | 로컬 stdio를 지원하는 MCP 클라이언트 연결, 상태·저장 공고·요약 조회, 수집 실행 |
| 예약 | 로컬 프로세스가 실행 중일 때 매일 09:00 Asia/Seoul 요약 파일 생성 |

잡코리아·캐치·자소설은 검색 단서와 수동 발견 경로입니다. 이 사이트들의 무허가 자동 수집기는 포함하지 않습니다. 회사 원문 수집 대상은 기본적으로 비어 있으며 허용 근거를 검토해 직접 설정해야 합니다. API 미연결·원문 미검증을 숨기지 않습니다.

## 설치

Python 3.11+를 사용하는 Windows·macOS·Linux를 지원합니다. 파일 잠금은 운영체제에 맞는 filelock 백엔드를 사용하며, Asia/Seoul 시간대 데이터도 패키지로 설치합니다.

macOS / Linux:

```sh
git clone https://github.com/ocean-all/career-discovery-mcp.git
cd career-discovery-mcp
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[mcp]'
cp .env.example .env
chmod 600 .env
python -m jobmonitor.cli search-links --query "관심 직무 관심 산업 채용"
python -m jobmonitor.cli demo
```

Windows PowerShell (가상환경 활성화 없이 실행):

```powershell
git clone https://github.com/ocean-all/career-discovery-mcp.git
cd career-discovery-mcp
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[mcp]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m jobmonitor.cli demo
```

사람인 검색 링크는 키 없이 사용합니다. 사람인 공식 API 자동 수집이나 네이버를 선택할 경우에만 **본인 키**를 로컬 `.env`에 입력합니다. 키 없이도 Google 검색 링크와 가상 공고 데모를 사용할 수 있습니다. 키·DB·보고서·가상환경은 저장소에 포함하지 않습니다. 개인 관심 프로필 `profile.json`도 제외합니다.

## MCP와 스킬 연결

Codex는 필수가 아닙니다. Claude Desktop, VS Code 등 **로컬 stdio 서버를 실행할 수 있는 클라이언트**에 연결할 수 있습니다. [클라이언트별 설정](docs/MCP.md)을 참고하세요. MCP 초기화 시 대화 지침도 전달하므로 별도 스킬 설치 없이 도구를 사용할 수 있습니다.

다음 자동 설치기는 Codex 사용자를 위한 선택 기능입니다. 프로젝트 가상환경의 Python으로 실행하세요.

```sh
python scripts/install-local-integration.py --dry-run
python scripts/install-local-integration.py
```

설치기는 본인 Codex 설정에 `career_discovery` stdio 서버를 추가하고 `career-discovery` 스킬을 복사합니다. 설치 경로를 자동으로 기록하며 다른 서버 설정을 유지합니다. 기존에 다른 경로의 동명 서버가 있으면 덮어쓰지 않고 중지합니다. Codex에서 연결을 다시 불러온 뒤 다음처럼 요청합니다.

> $career-discovery로 내가 원하는 직무와 산업을 구체화하고 검색 범위를 정해 줘.

| MCP 도구 | 역할 |
|---|---|
| `get_saramin_search_links` | 키 없는 사람인 공개 검색·Google 사이트 검색 링크 |
| `get_search_profile` | 저장된 초안/확정 관심 범위 읽기 |
| `save_search_profile` | 사용자 답과 확장 가설을 구분해 로컬 저장 |
| `build_search_plan` | 받아들인 범위로 검색 질의 생성 |
| `get_google_search_links` | 기본 30일, 선택 1–365일 Google 검색 링크 생성 |
| `get_status` | 키 존재 여부와 최근 실행 상태 |
| `list_jobs` | 저장된 공고 검색·점수·확인 수준 |
| `read_daily_summary` | 운영 요약과 당일 생성 여부 |
| `run_collection` | 설정된 공식 API·허용 회사 수집 실행 |
| `open_naver_discovery` | 사용자용 일시 네이버 검색 화면 시작 |

이 서버는 사용자의 컴퓨터에서 실행됩니다. 원격 호스팅·공유 URL·클라우드 ChatGPT 예약 연결을 제공하지 않습니다. MCP 등록이 스케줄러를 자동 시작하지 않습니다.

## 실행

```sh
python -m jobmonitor.cli search-links --days 30 --query '여행 서비스 기획 채용'
python -m jobmonitor.cli saramin-links --query "여행 서비스 기획"
python -m jobmonitor.cli run
python -m jobmonitor.cli report
python -m jobmonitor.cli discover
python -m jobmonitor.cli schedule
```

`run`은 사람인 키가 있으면 공식 API, 없으면 공개 검색 링크를 준비합니다. 허용 회사 원문은 설정한 범위에서 자동 조회합니다. 키가 없다는 이유로 실패하지 않으며, 실제 수집이 없는 실행은 `discovery_only`로 표시합니다. Google 검색과 네이버 결과를 자동 수집하지 않습니다. 보고서는 `reports/latest.md`, 운영 DB는 `data/jobs.sqlite`, 데모는 별도 DB·보고서에 저장됩니다. 종료 코드 0 실행 완료(자동 수집 범위는 상태 확인), 2 부분 실패, 3 실행 중입니다.

설정은 [사용·운영 안내](docs/USAGE.md), 키 신청과 조건은 [공급자 안내](docs/PROVIDERS.md), 다른 MCP 클라이언트 연결은 [MCP 안내](docs/MCP.md)를 참고하세요.

## 테스트

```sh
python -m pip install -e '.[mcp,documents]'
python -m unittest discover -s tests -v
```

API 응답 모형, SQLite, 문서 추출, 요청 제한과 비밀키 비노출, 실제 stdio 초기화/도구 호출을 테스트합니다. 테스트는 실제 API 키나 실공고를 요구하지 않습니다. 선택 패키지 미설치 시 관련 테스트는 생략됩니다. 실제 한국어 OCR과 사이트별 레이아웃은 원문 대조가 필요합니다.

## Sharing and License

The source code is distributed under the MIT License. This license does not grant rights to third-party API data, job postings, or search results. Follow each provider's terms and use your own credentials for optional API integrations. Never share API keys, personal profiles, databases, or reports in a public repository.

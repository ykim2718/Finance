# Skill Loading Rules (Mandatory)

Rev. 4 | Created: 2026-8-1 : Updated: 2026-8-11 12:45 CDT

아래 규칙은 최우선 적용된다. AI는 자체 판단으로 skill loading을 생략할 수 없으며, 조건에 해당하면 본 작업 수행 직전에 해당 skill을 반드시 먼저 load해야 한다.

1. Python Code Trigger (`coding_rules`)
   - **조건:** `.py` 파일의 작성(Write), 수정(Edit/Update), 생성, refactoring 등 파일 내용에 변동을 주는 모든 작업 실행 시
   - **필수 행동:** 코드를 작성하거나 수정하기 전에 `coding_rules` skill을 즉시 load할 것.

2. Markdown Document Trigger (`md_rules`)
   - **조건:** `.md` 파일의 작성(Write), 수정(Edit/Update), 생성 등 파일 내용에 변동을 주는 모든 작업 실행 시
   - **필수 행동:** markdown 문서를 작성하거나 수정하기 전에 `md_rules` skill을 즉시 load할 것.
   
2. Python Code Document Trigger (`python_md_rules`)
   - **조건:** 사용자가 Python 코드를 두고 "문서 만들어줘", "README 써줘", "API 정리해줘", "모듈 설명서", "docstring 기반 문서화" 등을 요청하면 반드시 이 스킬을 사용할 것. 'Markdown'이나 '문서'라는 단어를 쓰지 않더라도, 코드에 대한 설명 산출물을 파일로 요구하면 사용한다.
   - **행동:**; Python 소스(.py 파일, 패키지, 리포지토리)를 읽어 구조·공개 API·사용 예시를 정리한 Markdown 문서 (README, API 레퍼런스, 모듈 설명서)를 생성한다.
   - **제외:** 단, 코드 동작을 대화로 설명만 하는 경우, docstring·주석을 코드 안에 추가하는 경우, Python 이외의 언어는 대상이 아니다.




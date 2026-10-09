# Kelly and Shannon Study Handoff
Rev. 0 | Created: 2026-10-09 | Updated: 2026-10-09 22:36 UTC

- [1. Purpose](#1-purpose)
- [2. Summary](#2-summary)
- [3. Scope](#3-scope)
- [4. Method](#4-method)
- [5. Result](#5-result)
  - [5.1 Kelly Criterion](#51-kelly-criterion)
  - [5.2 Shannon's Demon](#52-shannons-demon)
  - [5.3 Environment](#53-environment)
- [6. Further Work](#6-further-work)
- [Appendix A. Terminology](#appendix-a-terminology)

## 1. Purpose

- **Problem Statement**: `Stock/Kelly-Criterion` 와 `Stock/Shannon-Demon` 두 study 를 고친 session 이 끝나면서, 끝낸 것과 막힌 것과 그 사이에 바뀐 작업 규칙이 대화에만 남아 있다.
- **Goal**: 다른 session 이 이 문서만 읽고 두 study 의 현재 판, 남은 과제, push 규칙, 실행 환경의 제약을 알아 같은 자리에서 이어서 고칠 수 있게 한다.
- **Non-Goal**: Kelly criterion 과 rebalancing bonus 의 원리는 다루지 않는다. 그것은 두 study 문서가 담는다.

## 2. Summary

Kelly criterion 문서는 Rev. 14, Shannon's demon 문서는 Rev. 11 로 `main` 의 `ecd69f2` 에 올라가 있다. 막힌 과제는 VIX 와 SOXL 의 6개월 1:1 chart 하나이며, 원인은 실행 환경의 network egress policy 가 시세 provider 를 막는 것이다. 두 문서는 `md_rules` Rev. 68 이 요구하는 목차·표 정렬·reference 서식·math fence·파일명을 아직 따르지 않는다.

## 3. Scope

이 session 에서 사용자가 요청한 것은 아래 다섯 가지다.

1. Shannon's demon 문서에 correlation 두 지점 사이의 bonus 차이를 수식으로 더하라.
2. Kelly 문서에 Appendix B 를 만들어 결정론적 가격 경로의 비중별 자산을 보여라.
3. Appendix B 의 가격 경로를 횡보하는 것으로 바꿔 다시 계산하라.
4. Fig 3 의 zone label 을 키우고 겹친 글씨를 읽히게 하라.
5. VIX 와 SOXL 의 최근 6개월 1:1 chart 를 그려라.

다섯 번째는 끝내지 못했다. 그 사유는 5.3 절에 있다. 나머지로 바뀐 파일은 넷이다.

Table 1. Files changed in this session

| Path                                       | Change                                                |
| :---:                                      | :---:                                                 |
| `Stock/Kelly-Criterion/Kelly_Criterion.md` | Appendix B 신설과 재작성, Fig 3 가독성, reference 추가 |
| `Stock/Kelly-Criterion/src/alternating.py` | 신규 script                                            |
| `Stock/Kelly-Criterion/src/kelly.py`       | Zone label 확대와 annotation 배경                      |
| `Stock/Shannon-Demon/Shannons_Demon.md`    | Correlation 두 지점 사이 bonus 차이 수식               |

Session 이 끝날 때 local 작업 tree 는 깨끗하고, `main` 은 `a954e71` 이다. 이 session 이 올린 마지막 commit 은 `ecd69f2` 이며, 그 뒤의 `25fc6ff` 와 `a954e71` 은 다른 session 이 올린 것이다.

## 4. Method

작업은 `main` 에 직접 commit 하고 push 한다. Session 중간에 사용자가 작업용 branch `claude/laughing-carson-yii7kg` 를 remote 에서 지웠고, 그 뒤 `main` 에만 push 하기로 정했다. 이 결정은 `md_rules` Rev. 68 section 16 에 같은 내용으로 들어가 있다.

Session 중에 `md_rules` 에 더한 규칙은 plugin 이 `plugins/yrocket-rules` 에서 `yrocket-md-doc` 으로 옮겨지면서 사라졌다. 두 문서는 그 네 줄을 따르고 있으므로, 서식을 고칠 때 아래를 알고 있어야 한다.

- Table caption 앞에 빈 줄 한 줄, figure caption 뒤에 빈 줄 한 줄.
- Figure caption 을 `<p>Fig N. title</p>` 로 감싼다. `<img>` 가 줄 첫머리에 오면 CommonMark 의 HTML block 이 다음 빈 줄까지 이어져, 감싸지 않으면 caption 이 `<p>` 없는 raw text 로 나와 아래쪽 여백이 0 이 된다.
- `<img>` 에 `display: block` 을 준다. 없으면 inline baseline 의 descender 만큼 그림 아래에 빈 자리가 생긴다.

수식의 별표는 `\ast` 로 적는다. 한 줄에 `*` 가 두 번 나오면 GitHub 이 그 사이를 강조로 보아 두 별표를 지우므로, `$f^{*}$` 는 `$f^{}$` 가 되어 깨진다. 이 규칙은 `md_rules` Rev. 68 section 9 에 남아 있다.

## 5. Result

### 5.1 Kelly Criterion

`Stock/Kelly-Criterion/Kelly_Criterion.md` 는 Rev. 14 이고 본문 4 꼭지와 Appendix 4 개를 담는다. 이 session 이 Appendix B 를 새로 만들고 한 번 다시 썼다.

Appendix B 는 이틀이 한 주기인 결정론적 가격 경로에서 비중별 자산을 따라간다. 주가는 1 에서 출발해 홀수 날 10% 내리고 짝수 날 $1/9$ 만큼 올라 정확히 1 로 돌아오며, 100일 동안 이를 되풀이한다. 투자금 100 에 대해 한 주기의 배수는 $1 + f(1-f)/90$ 이고, $f = 0.5$ 에서 최대이며 그 값이 2.3 절의 식이 주는 $f^{\ast}$ 와 같다.

Table 2. Appendix B wealth after 100 days

| Bet fraction | Two-day multiplier | Final wealth | Total return |
| :---:        | :---:              | :---:        | :---:        |
| 0.00         | 1.000000           | 100.0000     | 0.0000%      |
| 0.25         | 1.002083           | 110.9665     | +10.9665%    |
| 0.50         | 1.002778           | 114.8775     | +14.8775%    |
| 0.75         | 1.002083           | 110.9665     | +10.9665%    |
| 1.00         | 1.000000           | 100.0000     | 0.0000%      |

이 표는 `src/alternating.py` 가 만든다. 그 전 판은 홀수 날 10% 오르고 짝수 날 10% 내리는 경로여서 모든 비중이 손실이었고 $f^{\ast} = 0$ 이었으나, 사용자가 횡보 경로로 바꾸라고 하여 다시 썼다. `--first-day` option 으로 두 경로를 모두 그릴 수 있다.

Fig 3 의 zone label 네 개는 `ZONE_LABEL_SCALE = 1.5` 로 키웠고, 세 점의 annotation 에는 `facecolor='white', alpha=0.25` 인 bbox 를 깔아 fill 위에서도 읽히게 했다. 이 두 가지는 `src/kelly.py` 0.5.0 에 들어 있다.

Reference `[3]` 은 사용자가 제목·채널·연월을 알려 준 YouTube 영상이다. 실행 환경이 `www.youtube.com` 을 막아 page 를 열어 확인하지 못했으므로, 본문 인용은 영상의 주장을 옮기지 않고 "한국어로는 대중 매체에서도 소개되어 있다" 에 그친다.

### 5.2 Shannon's Demon

`Stock/Shannon-Demon/Shannons_Demon.md` 는 Rev. 11 이고 본문 6 꼭지와 Appendix 4 개를 담는다. 이 session 이 3.2 절 끝에 한 문단과 두 수식을 더했다.

더한 것은 correlation 두 지점 사이의 bonus 차이다. $\Delta \text{bonus} = w(1-w)\sigma^2(\rho_2 - \rho_1)$ 이고, volatility 20% 와 동일 비중에서 correlation 을 0.00 에서 +0.90 으로 올리면 $0.25 \times 0.04 \times 0.90 = 0.009000$ 이다. 이 값이 그 문서 Table 2 의 20% 행에서 1.00 %p 가 0.10 %p 로 떨어지는 폭이다.

이 문서에 Kelly 는 한 번도 나오지 않는다. 사용자가 이전 session 에서 Kelly 내용을 빼라고 했기 때문이며, 수식을 더할 때도 Kelly 식이 아니라 그 문서 자신의 rebalancing bonus 식을 썼다.

### 5.3 Environment

실행 환경의 network egress proxy 가 시세 provider 를 막는다. 이 session 에서 확인한 것은 아래와 같다.

Table 3. Reachability of data sources

| Host                         | Result |
| :---:                        | :---:  |
| `raw.githubusercontent.com`  | 열림   |
| `query1/2.finance.yahoo.com` | 막힘   |
| `stooq.com`                  | 막힘   |
| `www.alphavantage.co`        | 막힘   |
| `financialmodelingprep.com`  | 막힘   |
| `data.nasdaq.com`            | 막힘   |
| `api.stlouisfed.org`         | 막힘   |
| `doi.org`                    | 막힘   |
| `www.youtube.com`            | 막힘   |

VIX 는 `raw.githubusercontent.com` 의 `datasets/finance-vix` 에서 2026-09-22 까지 일별로 받을 수 있다. SOXL 은 받을 길이 없다.

저장소에는 `Stock/Kaggle/Stock-Market-Dataset/Stock/` 아래 1,134 종목의 일별 CSV 가 있으나 2020-04-01 에서 끝나며, SOXL 과 VIX 는 들어 있지 않다.

Remote branch 는 `git push origin --delete` 가 `fatal: the remote end hung up unexpectedly` 로 끝나 지울 수 없다. 2s, 4s, 8s 로 세 번 다시 시도해도 같았고, GitHub MCP 에도 branch 삭제 tool 이 없다.

## 6. Further Work

- **VIX 와 SOXL 의 6개월 1:1 chart**
  - 무엇을: 두 계열을 시작일 100 으로 정규화해 한 축에 겹쳐 그린다.
  - 왜 지금: 사용자가 요청했고 VIX 는 이미 받을 수 있다.
  - 필요한 것: SOXL 일별 CSV. 사용자가 올리거나, SOXL 을 주는 host 가 egress policy 에 열려야 한다.
- **두 study 문서를 `md_rules` Rev. 68 에 맞추기**
  - 무엇을: 목차를 넣고, 표 구분선을 `| :---: |` 로 바꾸고, reference 항목 사이의 빈 줄을 `<br>` 로 바꾸고, `$$` display 수식 12 개를 `math` fence 로 옮기고, 파일명에 `-ko` 를 붙인다.
  - 왜 지금: 두 문서는 본문이 한글인데 파일명에 `-ko` 가 없고, 나머지 네 가지는 Rev. 68 에서 새로 생긴 규칙이다.
  - 필요한 것: `md_rules` 의 `check_terms.py`, `check_refs.py`, `check_math_emphasis.py` 와 파일명을 바꿀 때 image folder 이름을 함께 바꾸는 일.
- **Reference 의 외부 link 확인**
  - 무엇을: Kelly 문서의 DOI 두 개와 YouTube link 를 실제로 열어 존재와 연관성을 확인한다.
  - 왜 지금: `md_rules` section 14 가 요구하는데 egress 가 막혀 이 session 에서 하지 못했다.
  - 필요한 것: `doi.org` 와 `www.youtube.com` 이 열린 실행 환경.
- **작업용 branch 삭제**
  - 무엇을: remote 의 `claude/laughing-carson-yii7kg` 를 지운다.
  - 왜 지금: 사용자가 지우기로 정했고 `main` 과 내용이 같다.
  - 필요한 것: GitHub web 화면. Session 에서는 ref 삭제 push 가 막힌다.

---

## Appendix A. Terminology

- **bet fraction**: 매 기간 위험 자산에 두는 자산의 비율. 나머지는 현금으로 둔다.
- **egress policy**: 실행 환경이 바깥으로 나가는 연결을 host 별로 허용하거나 막는 규칙.
- **rebalancing bonus**: 고정 비중을 되돌리는 행위가 만드는 log 성장률의 증가분.
- **zone label**: Kelly 문서 Fig 3 에서 비중 구간마다 붙인 Conservative, Aggressive, Over-aggressive, Insane 네 이름.

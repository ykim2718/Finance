# yRocket Finance Skills Session
Rev. 0 | Created: 2026-10-09 | Updated: 2026-10-09 22:05 UTC

- [1. Purpose](#1-purpose)
- [2. Summary](#2-summary)
- [3. Scope](#3-scope)
- [4. Method](#4-method)
  - [4.1 Repositories](#41-repositories)
  - [4.2 Data Sources](#42-data-sources)
  - [4.3 Conventions](#43-conventions)
- [5. Result](#5-result)
  - [5.1 Skills](#51-skills)
  - [5.2 Validation](#52-validation)
- [6. Further Work](#6-further-work)
- [Appendix A. Terminology](#appendix-a-terminology)

## 1. Purpose

- **Problem Statement**: 2026-10-04 부터 2026-10-09 까지의 session 에서 투자 방법 네 가지를 검증하고 skill 로 만들었지만, 검증 결과와 결정 사항이 대화에만 남아 있어 다른 session 이 이어받을 수 없다.
- **Goal**: 다른 session 이 이 문서만 읽고 skill 네 개의 위치와 기본값, 검증 결과, 실행 환경의 제약, 남은 과제를 파악해 작업을 이어 갈 수 있게 한다.
- **Non-Goal**: 각 skill 의 사용법과 script 의 내부 구현은 다루지 않는다.

## 2. Summary

`yrocket-finance` plugin 에 skill 네 개를 만들어 `ykim2718/Claude-Configuration` 의 main 에 올렸으며, 마지막 commit 은 `ea69299` 이다. 말릭 TQQQ 전략은 매도 뒤 10 거래일 동안 다시 사지 않는 규칙을 더하자 10 년 CAGR 28.8%, MDD −35.3% 로 규칙이 없을 때보다 나았고, Dave Siegel screen 은 5 년 동안 꾸준한 초과 수익을 내지 못했다. 남은 과제는 section 6 에 있다.

## 3. Scope

사용자가 이 session 에서 요청한 일과 그 결과는 아래와 같다.

Table 1. Requests in this session

| No  | Request                                                                       | Outcome                                                 |
| :-: | :---------------------------------------------------------------------------: | :-----------------------------------------------------: |
| 1   | Dave Siegel 방법: 한 달 거래량 3 배 이상, 주가 상승 3% 미만, 사건성 급증 제외 | 후보 HGTY·BWIN 이 공모와 M&A 로 제외되어 통과 종목 없음 |
| 2   | 조건 변경: mid-cap 이상, 네 sector, Finance 제외, 거래량 2 배, 주가 0~5%      | NEOG 통과, TH·INGM 은 지분 매각 공모로 제외             |
| 3   | 최근 5 일 상승 종목을 따로 강조하는 조건을 넣어 skill 로 등록                 | `dave-siegel-stock-trading`                             |
| 4   | Plugin `yrocket-finance` 를 만들어 skill 을 저장                              | Claude-Configuration 의 marketplace 에 등록             |
| 5   | Finance repo 에 plugin 설정 추가                                              | `.claude/settings.json` 과 `.gitignore` 예외, `25fc6ff` |
| 6   | 말릭 TQQQ 전략 5 년 backtest, 현재 배열 확인, skill 등록                      | `malik-tqqq-trading`                                    |
| 7   | 매매 금지 기간 비교와 10 년 검증, 기본값 변경, Backtest 꼭지                  | 기본값을 매도 뒤 10 거래일 금지로 변경                  |
| 8   | Dave Siegel skill 에 Backtest 꼭지                                            | `scripts/backtest.py` 와 5 년 결과                      |
| 9   | 13F 유명 투자자 여섯 명의 공통 보유 종목과 공통 매수 종목, skill 등록         | `13f-common-buys`                                       |
| 10  | 비트코인 월별 등락의 원인 분석과 skill 등록                                   | `bitcoin-move-drivers`                                  |

## 4. Method

### 4.1 Repositories

작업물은 두 저장소에 있다.

Table 2. Repositories

| Repository                    | Branch | Content                                                               |
| :---------------------------: | :----: | :-------------------------------------------------------------------: |
| ykim2718/Claude-Configuration | main   | `plugins/yrocket-finance/`, `.claude-plugin/marketplace.json`, README |
| ykim2718/Finance              | main   | `.claude/settings.json`, 이 문서                                      |

- `yrocket-finance` 의 skill 은 `plugins/yrocket-finance/skills/<skill>/SKILL.md` 와 `scripts/` 로 이루어진다.
- Finance 의 `.claude/settings.json` 은 `claude-configuration` marketplace 의 `yrocket-md-doc`, `yrocket-coding`, `yrocket-finance` 를 켠다. `.gitignore` 는 `.claude/` 아래에서 이 파일만 추적한다.
- Session 이 시작될 때 설치된 plugin cache 는 그 시점의 marketplace 판이다. 이 session 의 cache 에는 `yrocket-finance` 가 없었으므로, 새 session 에서 skill 네 개가 목록에 보이는지 먼저 확인한다.

### 4.2 Data Sources

쓴 자료원과 접근 가능 여부는 아래와 같다.

Table 3. Data sources

| Source                                    | Used for                                           | Access                                      |
| :---------------------------------------: | :------------------------------------------------: | :-----------------------------------------: |
| api.nasdaq.com                            | 종목 목록, 주식·ETF·COMP·BTC 의 일별 종가와 거래량 | 허용, User-Agent 필요                       |
| data.sec.gov, www.sec.gov                 | 13F-HR 원본                                        | 사용자가 Network access 를 Custom 으로 허용 |
| WebSearch                                 | 거래량 급증과 가격 등락의 원인이 된 뉴스           | 허용                                        |
| Yahoo Finance, CoinGecko, Binance, Kraken | 가격 자료                                          | proxy 가 차단                               |
| Dataroma, 13f.info, WhaleWisdom           | 13F 요약                                           | proxy 가 차단                               |

- Nasdaq API 의 종가는 split 조정 값이다. TQQQ 의 2020-03-16 −34% 와 2025-04-09 +35% 는 실제 시장 변동이다.
- Network access 는 claude.ai/code 의 메시지 입력창 바로 위 줄에 있는 구름 아이콘에서 환경의 톱니바퀴를 눌러 바꾼다.

### 4.3 Conventions

- Python script 는 `yrocket-coding` 의 `coding_rules` 를 따른다. `__author__ = 'yRocket'`, `Major.Minor.Patch+YYYYMMDD` 형식의 `__version__`, argparse 의 `-v` 와 `--output-folder` 를 둔다.
- Markdown 은 `yrocket-md-doc` 의 `md_rules` 와 `tech_doc_design` 을 따르고, 고친 뒤 `check_terms.py` 와 `check_refs.py` 를 돌린다.
- Push 는 `md_rules` section 16 에 따라 main 에 한다. Finance 의 작업 branch `claude/clever-euler-kinibv` 는 main 과 같은 commit 으로 맞춘다.
- SEC 에 요청할 때는 연락처가 든 User-Agent 를 `--user-agent` 로 넘긴다.

## 5. Result

### 5.1 Skills

`yrocket-finance` 의 skill 과 기본값은 아래와 같다.

Table 4. Skills in yrocket-finance

| Skill                     | Script                 | Default                                                                                  | Commit    |
| :-----------------------: | :--------------------: | :--------------------------------------------------------------------------------------: | :-------: |
| dave-siegel-stock-trading | screen.py, backtest.py | mid-cap 이상, 네 sector, Finance 제외, 거래량 2 배 이상, 한 달 주가 0~5%, 5 일 상승 강조 | `7a21f45` |
| malik-tqqq-trading        | backtest.py            | COMP > SMA50 > SMA250 이면 TQQQ 보유, 다음 거래일 종가 체결, 매도 뒤 10 거래일 매수 금지 | `cccb979` |
| 13f-common-buys           | common_buys.py         | 여섯 명, NEW 2 명 이상, NEW 또는 ADDED 3 명 이상                                         | `32548f4` |
| bitcoin-move-drivers      | monthly_moves.py       | 최근 5 년, 등락이 큰 8 개월, 원인을 다섯 요인으로 분류                                   | `ea69299` |

- 네 sector 는 Nasdaq 분류의 Industrials, Technology, Health Care, Consumer Discretionary 이다. Nasdaq 분류에는 Manufacturing 이 없어, 제조업 종목은 Industrials, Technology, Consumer Discretionary 에 나뉘어 들어 있다.
- 여섯 명은 Buffett, Ackman, Druckenmiller, Tepper, Klarman, Dalio 이다.
- 다섯 요인은 금리·유동성, 기관 자금, 업계 내부 사고, 정치·규제, 레버리지 청산이다.

### 5.2 Validation

Dave Siegel screen 의 5 년 backtest 에서는 꾸준한 초과 수익이 나오지 않았다. 2021-09 부터 2026-06 까지 21 거래일마다 조건을 적용해 125 건이 걸렸고, 63 거래일 뒤 수익의 평균은 13.7% 로 비교 대상 universe 의 4.1% 보다 높았지만 중앙값은 1.7% 로 universe 의 5.3% 보다 낮았다. 상위 3 건 (SBET, AXTI, IMVT) 을 빼면 평균은 2.9% 로 떨어진다. 이 backtest 에는 뉴스로 사건을 거르는 단계가 빠져 있고, 지금 상장된 mid-cap 이상 종목만 대상으로 해 survivorship bias 가 있다.

말릭 TQQQ 전략의 결과는 아래와 같다. 모두 다음 거래일 종가 체결, 매매당 5 bp 비용, 현금 수익 0 으로 계산했다.

Table 5. Malik TQQQ results

| Rule                    | Period            | CAGR % | MDD % |
| :---------------------: | :---------------: | :----: | :---: |
| 매도 뒤 10 일 금지      | 2016-10 ~ 2026-10 | 28.8   | −35.3 |
| 금지 없음               | 2016-10 ~ 2026-10 | 20.9   | −45.7 |
| TQQQ buy-and-hold       | 2016-10 ~ 2026-10 | 40.8   | −81.8 |
| 매도 뒤 10 일 금지      | 2016-10 ~ 2021-10 | 30.2   | −35.3 |
| 금지 없음               | 2016-10 ~ 2021-10 | 19.2   | −45.7 |
| 매도 뒤 10 일 금지      | 2021-10 ~ 2026-10 | 27.4   | −32.0 |
| 금지 없음               | 2021-10 ~ 2026-10 | 22.7   | −34.6 |
| 모든 매매 뒤 21 일 금지 | 2021-10 ~ 2026-10 | 16.9   | −46.3 |

- 10 일이라는 값은 2021-10 ~ 2026-10 구간의 비교로 골랐다. 고를 때 쓰지 않은 2016-10 ~ 2021-10 구간에서도 10 일 금지가 금지 없음보다 나았다.
- 매수 뒤에도 금지 기간을 두면 산 직후 배열이 깨져도 팔 수 없어 손실이 커졌다.
- 신호가 난 날의 종가에 체결하면 10 년 CAGR 이 24.7%, MDD 가 −45.1% 로 나빠진다.
- 2026-10-02 종가 기준 배열은 지수 > SMA50 > SMA250 이었고, 매도 뒤 10 일 규칙으로는 2026-09-30 부터 TQQQ 를 보유하는 상태였다.

13F 의 2026-06-30 기준 결과는 아래와 같다.

- 여섯 명이 모두 가진 종목은 없고, 다섯 명이 가진 종목은 Alphabet (Ackman 제외) 과 Amazon (Buffett 제외) 이다.
- 2026 년 2 분기에 두 명 이상이 새로 산 종목은 D.R. Horton, Boeing, SpaceX, Rocket Companies, FTAI Aviation 이다.
- 새로 사거나 더 산 투자자가 세 명 이상인 종목은 Alphabet, D.R. Horton, Amazon, Delta Air Lines 이다.
- Ackman 의 2026 년 2 분기 13F 는 Pershing Square Inc. (CIK 2026053) 가, 1 분기 13F 는 Pershing Square Capital Management (CIK 1336528) 가 냈다.

비트코인은 2021-10 ~ 2026-09 동안 금리·유동성, 기관 자금, 업계 내부 사고, 정치·규제의 네 요인이 큰 등락을 일으켰고, 레버리지 청산이 그 폭을 키웠다. 2026-09 는 현물 ETF 에 26 억 5 천만 달러가 들어와 +6.4% 였다. 2026-10 초에는 10-27~28 FOMC 의 금리 인상 가능성, 배럴당 100 달러를 넘은 유가, ETF 유입 둔화가 하락 쪽으로 작용하고 있었다.

## 6. Further Work

1. **Plugin 반영 확인**: 새 session 에서 `yrocket-finance` 의 skill 네 개가 목록에 보이는지 확인한다. 이 session 의 plugin cache 는 `yrocket-finance` 를 만들기 전 판이었다. 필요한 것은 Finance repo 로 여는 새 session 이다.
2. **Dave Siegel 뉴스 거르기 backtest**: 지금 backtest 는 거래량과 주가 조건만 적용했다. 사건성 급증을 거른 성과를 재려면 과거 시점의 공시 자료가 필요하며, SEC 8-K 를 찾는 `efts.sec.gov` 를 Network access 에 더해야 한다.
3. **Dave Siegel survivorship bias 제거**: 상장 폐지 종목과 과거 시가총액이 든 자료가 필요하다. Nasdaq API 는 지금 상장된 종목만 준다.
4. **말릭 전략의 더 이른 구간 검증**: TQQQ 가 상장한 2010-02 부터 2016-10 까지 매도 뒤 10 일 규칙을 검증한다. Nasdaq API 가 10 년보다 긴 자료를 주는지 먼저 확인해야 한다.
5. **13F 정정 보고서 반영**: `13f-common-buys` 는 13F-HR/A 를 쓰지 않는다. 정정 보고서를 자주 내는 투자자를 더할 때 필요하다.
6. **비트코인 2026-10 원인 기록**: 10-27~28 FOMC 뒤 10 월의 등락률과 원인을 확인해 `bitcoin-move-drivers` 의 원인 표에 더한다.

---

## Appendix A. Terminology

- **13F**: 운용자산 1 억 달러를 넘는 미국 기관 투자자가 분기마다 SEC 에 내는 보유 종목 보고서 (Form 13F-HR)
- **ADDED**: 직전 분기보다 주식 수가 늘어난 종목
- **CAGR**: 연평균 복리 수익률 (compound annual growth rate)
- **COMP**: Nasdaq Composite 지수
- **MDD**: 고점에서 저점까지의 가장 큰 하락률 (maximum drawdown)
- **NEW**: 직전 분기에 없다가 이번 분기 13F 에 처음 나온 종목
- **SMA**: 단순 이동평균 (simple moving average), 거래일 수로 센다
- **survivorship bias**: 지금 남아 있는 종목만 대상으로 해 과거 성과가 실제보다 좋게 나오는 치우침

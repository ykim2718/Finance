# Klomagi Study Handoff
Rev. 0 | Created: 2026-10-09 | Updated: 2026-10-09 21:58 UTC

- [1. Purpose](#1-purpose)
- [2. Summary](#2-summary)
- [3. Scope](#3-scope)
- [4. Method](#4-method)
- [5. Result](#5-result)
  - [5.1 Base rule](#51-base-rule)
  - [5.2 Variant search](#52-variant-search)
- [6. Analysis](#6-analysis)
- [7. Further Work](#7-further-work)
- [References](#references)
- [Appendix A. Terminology](#appendix-a-terminology)

## 1. Purpose

- **Problem Statement**: 클로마기 기법의 검증과 개선 탐색이 끝났으나, 어떤 수치를 어떤 조건에서 얻었고 무엇이 아직 문서에 실리지 않았는지가 이전 session 의 대화에만 남아 있다.
- **Goal**: 다른 session 이 이 문서만 읽고 지금까지의 측정값, 산출물의 위치, 실행 방법, 남은 과제를 이어받아 같은 계산을 되풀이하고 다음 단계를 시작할 수 있게 한다.
- **Non-Goal**: 기법의 원리와 매매 조건은 다루지 않는다. 매수·매도 권고도 다루지 않는다.

## 2. Summary

Base 조건의 계좌는 2013-02-08 ~ 2018-02-07 표본에서 연 6.83% 로, 같은 기간 S&P 500 지수의 12.06% 에 못 미쳤다. 손절 제거·문턱값 완화·유휴 자본의 지수 투입을 합치면 연 16.19% 로 지수를 넘지만, 같은 규칙에 진입일만 무작위로 바꾼 대조군이 15.68% 이므로 그 이득은 진입 조건의 몫이 아니다. 산출물은 이 문서와 같은 folder 에 있으며, 개선 탐색의 결과는 아직 `klomagi-ko.md` 에 실리지 않았다.

## 3. Scope

이전 session 에서 사용자가 요청한 것은 아래 여섯 가지이며, 모두 끝났다.

1. 클로마기 기법을 정리한 md 문서를 만들고 주가 자료로 한 backtest 결과를 Appendix 에 넣는다.
2. 누적 수익률과 연환산 수익률을 계산해 문서에 넣는다.
3. S&P 500 지수 수익률과 견주고 그 결과를 시계열 chart 로 보인다.
4. Appendix A 의 용어 목록에 equal weight index 를 더한다.
5. 신호 계좌가 S&P 500 지수를 이기게 만드는 방법을 찾는다.
6. 산출물을 WordPress 저장소에서 Finance 저장소로 옮기고 `src/` 구조에 맞춘다.

산출물은 아래와 같다. 경로는 이 문서가 있는 folder 를 기준으로 한다.

Table 1. Deliverables

| Path                                                 | Content                                                           |
| :---:                                                | :---:                                                             |
| `klomagi-ko.md`                                      | 기법 문서 Rev. 4. 원리, 매수 조건, backtest, backtest script 전문 |
| `klomagi-ko_fig/fig1.png`                            | 매매 수익 분포, 조건 조합별 평균 수익과 초과수익 세 panel         |
| `klomagi-ko_fig/fig2.png`                            | 신호·무작위 진입·S&P 500·등가중 지수 네 계좌의 equity 시계열      |
| `klomagi-ko_fig/{trades,grid,equity}.csv`            | 매매 명세, 조건 조합별 집계, 네 계좌의 일별 수익                  |
| `klomagi-ko_fig/summary.json`                        | 표본·조건·per trade 통계·portfolio 통계                           |
| `klomagi-ko_fig/klomagi_improve/fig3.png`            | 상위 변형 세 개와 최적 변형의 무작위 진입 대조군 equity 시계열    |
| `klomagi-ko_fig/klomagi_improve/variants.{csv,json}` | 18개 변형의 집계와 대조군 결과                                    |
| `src/klomagi_backtest.py`                            | 기법 backtest 와 대조군, equity 계산, Fig 1 과 Fig 2 생성         |
| `src/klomagi_improve.py`                             | 18개 변형 탐색, 최적 변형의 대조군, Fig 3 생성                    |

이 과제의 마지막 commit 은 Finance 의 `b624be0` 이고, WordPress 는 `1d72fcb` 에서 `Stock/` 을 지워 이 과제와 무관해졌다.

## 4. Method

주가는 S&P 500 505종목의 일별 OHLCV 619,029행을 썼고 [[1](#ref-1)], 지수는 같은 날짜의 일별 종가를 따로 읽었다 [[2](#ref-2)]. 실행 환경의 proxy 가 `query2.finance.yahoo.com`, `stooq.com`, `finance.naver.com`, `fred.stlouisfed.org`, `alphavantage.co` 를 모두 403 으로 막아 `yfinance` 를 쓸 수 없었고, 열려 있는 곳은 `raw.githubusercontent.com` 과 `pypi.org` 뿐이었다. 두 자료 모두 GitHub 의 공개 dataset 이며 2026-10-09 에 다시 받아 200 을 확인했다.

Backtest 는 세 부분으로 되어 있다. 신호는 5일·20일·60일·120일 이동평균이 뭉친 뒤 거래량과 장대양봉을 동반해 그 위를 뚫은 날이고, 매수는 다음 날 시가, 매도는 뭉치 하단을 깬 다음 날 시가와 60 거래일 한도 중 먼저 오는 쪽이다. 대조군은 같은 종목에서 신호 건수의 10배만큼 진입일을 균일 무작위로 뽑아 같은 매도 규칙으로 청산한 매매이며, 두 계좌의 차이가 진입 조건의 값이다. 계좌는 그날 열려 있는 매매에 자본을 균등 배분하고 열린 매매가 없는 날은 현금으로 둔 것으로 계산했다.

두 script 는 모두 option 없이 실행하면 사용법을, `-v` 로 version 을 보인다. 아래 명령은 이 문서가 있는 folder 를 기준으로 하며, `--data-csv` 와 `--index-csv` 가 가리키는 파일이 없으면 References 의 주소에서 내려받는다.

```bash
python3 src/klomagi_backtest.py --data-csv all_stocks_5yr.csv --index-csv sp500-2000.csv \
    --output-folder klomagi-ko_fig
python3 src/klomagi_improve.py --data-csv all_stocks_5yr.csv --index-csv sp500-2000.csv \
    --output-folder klomagi-ko_fig/klomagi_improve
```

무작위 진입일은 `--seed` 로 고정되며, 아래 수치는 모두 기본값 20260910 으로 얻은 것이다.

## 5. Result

### 5.1 Base rule

Base 조건은 수렴 3%, 거래량 2.0배, 몸통 3%, 보유 한도 60 거래일이다.

Table 2. Per trade statistics of the base rule

| Metric              | Signal | Random entry |
| :---:               | :---:  | :---:        |
| Trades              | 174    | 1,289        |
| Win rate (%)        | 48.85  | 43.37        |
| Mean return (%)     | 2.532  | 1.399        |
| Mean excess (%)     | 0.354  | 0.195        |
| Mean holding (days) | 42.5   | 32.5         |

원수익의 차이 +1.13%p 는 Welch t=1.37, 지수 수익을 뺀 초과수익의 차이 +0.16%p 는 t=0.23 이다. 문턱값을 완화해 신호를 606건으로 늘리면 원수익 차이가 t=2.88 로 커지지만 초과수익 차이는 t=0.86 에 머문다.

Table 3. Portfolio result of the base rule, 2013-02-08 to 2018-02-07

| Metric                | Signal | Random entry | S&P 500 index | Equal weight index |
| :---:                 | :---:  | :---:        | :---:         | :---:              |
| Cumulative return (%) | 39.12  | 69.19        | 76.67         | 90.18              |
| Annualized return (%) | 6.83   | 11.10        | 12.06         | 13.73              |
| Max drawdown (%)      | -18.50 | -17.90       | -14.16        | -16.71             |
| Mean open positions   | 6.0    | 34.3         | 1.0           | 1.0                |

### 5.2 Variant search

문턱값 세 벌, 손절 세 가지, 유휴 자본을 두는 두 곳을 곱한 18개 변형 가운데 10개가 S&P 500 지수의 연 12.06% 를 넘었다.

Table 4. Variants with the highest annualized return

| Variant               | Thresholds                        | Stop  | Idle capital | Trades | Cumulative (%) | Annualized (%) | Max drawdown (%) |
| :---:                 | :---:                             | :---: | :---:        | :---:  | :---:          | :---:          | :---:            |
| loose/none/index      | 수렴 5%, 거래량 1.5배, 한도 60일  | 없음  | 지수         | 575    | 111.67         | 16.19          | -14.21           |
| loose/none/cash       | 수렴 5%, 거래량 1.5배, 한도 60일  | 없음  | 현금         | 575    | 108.79         | 15.88          | -14.28           |
| loose-long/none/index | 수렴 5%, 거래량 1.5배, 한도 120일 | 없음  | 지수         | 550    | 101.31         | 15.03          | -19.37           |

최적 변형 `loose/none/index` 의 진입일만 무작위로 바꾼 대조군은 누적 107.01%, 연환산 15.68%, 최대 낙폭 -20.27% 였다. 변경 하나씩의 효과는 손절 제거가 연 6.83% 에서 11.36%, 문턱값 완화가 14.26%, 유휴 자본의 지수 투입이 13.12% 이며, 셋을 합치면 16.19% 다.

## 6. Analysis

이 과제의 결론은 클로마기 조건이 승률만 높인다는 것이다. 20일 보유 기준 승률은 신호가 53~63%, 무작위 진입이 42~49% 로 18개 조건 조합 모두에서 신호가 높았으나, 지수 수익을 뺀 초과수익의 차이는 어느 표본에서도 t 값이 1 을 넘지 않았다. 연환산 16.19% 를 만든 세 가지 변경도 대조군에 0.51%p 앞설 뿐이므로, 좋아진 것은 진입 시점이 아니라 보유 종목 수와 보유 기간과 유휴 자본을 두는 곳이다.

수치를 그대로 믿기 어렵게 하는 조건이 세 가지 있다. 18개 변형을 같은 표본에서 골랐으므로 최적 변형의 성적에는 선택 편향이 들어 있고, 표본의 505종목은 구간 끝에 남은 종목만 담아 등가중 지수가 S&P 500 보다 13.51%p 높으며, 2013-2018 은 상승장이라 손절을 없앤 쪽이 유리하다.

`klomagi-ko.md` 에는 base 조건의 backtest 까지만 들어 있고, 5.2 의 변형 탐색 결과와 Fig 3 은 산출물 파일로만 남아 있다.

## 7. Further Work

- **변형 탐색 결과를 기법 문서에 싣기** — 5.2 의 Table 4 와 Fig 3 을 `klomagi-ko.md` 의 Appendix B 에 B.6 으로 더하고, Summary 와 Comparison 의 결론을 대조군 수치와 함께 고친다. 측정이 이미 끝났고 산출물이 folder 에 있으므로 새 계산 없이 쓸 수 있다.
- **국내 시장 자료로 재검증** — 기법은 국내 시장에서 쓰이는데 표본은 S&P 500 이다. 가격제한폭과 거래량 쏠림이 다르므로 돌파의 성질도 다르다. KRX 일별 OHLCV 와 상장폐지 종목을 포함한 종목 목록, 그리고 그 자료에 닿는 proxy 설정이 있어야 한다.
- **매도 규칙의 분리 검증** — 손절 제거가 가장 큰 효과를 냈으므로 매도 규칙이 다음 차례다. 진입 조건을 고정하고 손절선과 보유 한도만 바꾼 비교이며, 추가 자료 없이 같은 표본으로 할 수 있다.

## References

<a id="ref-1"></a>
[1] Plotly. [S&P 500 daily prices, 2013-02-08 to 2018-02-07 (`all_stocks_5yr.csv`)](https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv). plotly/datasets repository.<br>
<a id="ref-2"></a>
[2] Vega. [S&P 500 index daily prices since 2000 (`sp500-2000.csv`)](https://raw.githubusercontent.com/vega/vega-datasets/main/data/sp500-2000.csv). vega/vega-datasets repository.

---

## Appendix A. Terminology

- **base 조건**: 기법 문서가 기준으로 삼은 조건 한 벌. 수렴 3%, 거래량 2.0배, 몸통 3%, 보유 한도 60 거래일.
- **equal weight index**: 표본의 505종목을 매일 같은 비중으로 들고 있는 가상의 계좌. 하루 수익은 그날 값이 있는 모든 종목의 종가 수익률의 단순 평균이다.
- **excess return**: 매매 수익에서 같은 진입일·청산일 사이 등가중 지수 수익을 뺀 값.
- **max drawdown**: 계좌 잔고가 그때까지의 최고점 대비 가장 크게 줄어든 폭.
- **Welch t**: 분산이 다른 두 집단의 평균 차이를 검정하는 t 통계량.
- **장대양봉**: 시가보다 종가가 크게 높아 몸통이 긴 양봉.

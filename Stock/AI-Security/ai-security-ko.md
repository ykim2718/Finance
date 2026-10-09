# AI Security Stock Screen
Rev. 0 | Created: 2026-10-09 | Updated: 2026-10-09 21:51 UTC

- [1. Purpose](#1-purpose)
- [2. Summary](#2-summary)
- [3. Scope](#3-scope)
- [4. Method](#4-method)
- [5. Result](#5-result)
  - [5.1 Volume](#51-volume)
  - [5.2 News](#52-news)
- [6. Further Work](#6-further-work)
- [References](#references)
- [Appendix A. Terminology](#appendix-a-terminology)

## 1. Purpose

- **Problem Statement**: AI 발전으로 늘어나는 보안침해를 막는 기술을 파는 미국 상장 기업 가운데, 최근 한 달 동안 거래량과 긍정 뉴스가 함께 늘어난 기업을 가려야 한다.
- **Goal**: 다른 session 이 이 문서만 읽고 대상 종목, 계산 방법, 2026-10-05 기준 결과, 남은 과제를 이어받아 같은 계산을 되풀이할 수 있게 한다.
- **Non-Goal**: 매수·매도 권고와 기업 가치 평가는 다루지 않는다.

## 2. Summary

최근 21 거래일 평균 거래량이 그 앞 63 거래일 평균의 2배 이상인 AI 보안 기업은 2026-10-05 기준으로 없다. 가장 높은 Zscaler 도 1.19배였고, 같은 기간 일곱 종목의 주가는 13.5~28.4% 올랐다. 긍정 뉴스는 2026-09-14 AI 안전 경고 뒤의 보안주 상승을 따라 CrowdStrike, Okta, Palo Alto Networks, SentinelOne, Cloudflare 에 몰렸다.

## 3. Scope

이 session 에서 사용자가 물은 것은 아래 세 가지다.

1. AI 발전으로 인한 보안침해를 막는 기술을 파는 미국 주식은 무엇인가.
2. 그 가운데 최근 한 달 동안 매수량이 2배 이상 늘어난 기업은 무엇인가.
3. 그 가운데 최근 한 달 동안 긍정 뉴스가 늘어난 기업은 무엇인가.

대상은 아래 일곱 종목이다.

Table 1. Target stocks

| Ticker | Company            | Security area                    |
| :---:  | :---:              | :---:                            |
| CRWD   | CrowdStrike        | Endpoint, AI-driven platform     |
| PANW   | Palo Alto Networks | Network, platform                |
| ZS     | Zscaler            | Cloud, zero trust                |
| S      | SentinelOne        | Endpoint, AI-driven platform     |
| FTNT   | Fortinet           | Network, firewall                |
| OKTA   | Okta               | Identity, AI agent identity      |
| NET    | Cloudflare         | Network, cloud, AI model defense |

자료의 기준일은 2026-10-05 종가이며, 거래량은 그날까지 83 거래일 분량을 썼다.

## 4. Method

매수량만 따로 집계한 공개 자료가 없으므로 전체 거래량으로 대신했다. 거래량 배수는 최근 21 거래일 평균 거래량을 그 앞 63 거래일 평균 거래량으로 나눈 값이고, 주가 변화는 마지막 종가를 22 거래일 전 종가로 나눈 값에서 1 을 뺀 것이다.

실행 환경의 proxy 가 `query2.finance.yahoo.com` 과 `fc.yahoo.com` 을 막아 `yfinance` 는 쓸 수 없었다. 같은 자료를 Yahoo chart API 에서 종목마다 받았으며, `Too Many Requests` 가 오면 몇 초 쉬고 다시 받는다.

```bash
# bash
for s in CRWD PANW ZS S FTNT OKTA NET; do
  curl -sS -m 20 -A "Mozilla/5.0" \
    "https://query1.finance.yahoo.com/v8/finance/chart/$s?range=4mo&interval=1d" -o "$s.json"
done
```

받은 JSON 의 `chart.result[0].indicators.quote[0]` 에서 `volume` 과 `close` 를 읽고, 빈 값을 뺀 뒤 위 두 값을 계산한다.

긍정 뉴스는 web search 로 2026년 9월의 보안주 기사를 찾아 판단했다. 기사 수를 세어 비교한 것은 아니다.

## 5. Result

### 5.1 Volume

Table 2. One-month volume ratio and price change

| Ticker | Volume ratio | Price change |
| :---:  | :---:        | :---:        |
| ZS     | 1.19         | +13.5%       |
| S      | 1.18         | +28.4%       |
| OKTA   | 1.15         | +28.1%       |
| CRWD   | 1.02         | +26.8%       |
| PANW   | 0.92         | +22.5%       |
| NET    | 0.89         | +26.4%       |
| FTNT   | 0.71         | +17.8%       |

일곱 종목 모두 거래량 배수가 2 에 못 미친다. 거래량은 평소 수준인데 주가가 13.5~28.4% 올랐다.

### 5.2 News

Table 3. Positive news in September 2026

| Ticker | Event                                                  | Source                                      |
| :---:  | :---:                                                  | :---:                                       |
| CRWD   | 실적 기록, 2026-09-14 약 14% 상승으로 최고가           | [[1](#ref-1)], [[2](#ref-2)], [[3](#ref-3)] |
| OKTA   | 약 20% 급등, AI agent 신원 보안 부각                   | [[2](#ref-2)], [[4](#ref-4)]                |
| PANW   | 2026-09-14 약 13% 상승                                 | [[1](#ref-1)], [[3](#ref-3)]                |
| S      | 9월 중순 14% 상승, fiscal Q2 ARR 22% 성장              | [[5](#ref-5)]                               |
| NET    | 2026-09-09 OpenAI 와 만든 보안 서비스 출시로 10% 상승  | [[6](#ref-6)]                               |

2026-09-14 AI 기업 경영진이 AI 개발 속도에 대한 위험을 경고한 뒤, AI 와 반도체 주식은 내리고 보안주는 올랐다 [[1](#ref-1)]. 보안주의 강세는 9월 하순까지 이어졌다 [[4](#ref-4)].

## 6. Further Work

- **매수 거래량 집계**
  - 무엇을: 전체 거래량 대신 매수 체결량 또는 block trade 를 비교한다.
  - 왜 지금: 이번 계산은 매수량을 전체 거래량으로 대신했다.
  - 필요한 것: 체결 방향이 든 tick 자료나 유료 data feed.
- **뉴스 수 집계**
  - 무엇을: 종목마다 한 달 전과 최근 한 달의 긍정 기사 수를 세어 비교한다.
  - 왜 지금: 이번 판단은 검색 결과를 읽은 것이고 기사 수를 센 것이 아니다.
  - 필요한 것: 날짜와 종목으로 거를 수 있는 news API 와 sentiment 분류 기준.
- **대상 확대**
  - 무엇을: Rapid7, Tenable, Varonis, Check Point 같은 다른 보안주를 같은 계산에 넣는다.
  - 왜 지금: 일곱 대형주에서는 2배 거래량 종목이 없었다.
  - 필요한 것: Section 4 의 API 와 종목 목록.

## References

<a id="ref-1"></a>[1] Yahoo Finance (2026). [Crowdstrike, Palo Alto Networks, and cybersecurity stocks post strong weekly gains after AI freak-out moment](https://finance.yahoo.com/markets/article/crowdstrike-palo-alto-networks-and-cybersecurity-stocks-post-strong-weekly-gains-after-ai-freak-out-moment-142352398.html).<br>
<a id="ref-2"></a>[2] MatterFact (2026-09-08). [CrowdStrike Posts a Record Quarter as Okta Jumps 20 Percent](https://www.matterfact.com/newsletter/2026-09-08-crowdstrike-record-quarter-okta-jumps).<br>
<a id="ref-3"></a>[3] TradingKey (2026). [Cybersecurity Stocks Surge, CrowdStrike Jumps 15% as AI Risks May Drive Demand](https://www.tradingkey.com/analysis/stocks/us-stocks/262166964-cybersecurity-crowdstrike-palo-alto-okta-ai-slowdown-semiconductor-tradingkey).<br>
<a id="ref-4"></a>[4] 24/7 Wall St. (2026-09-23). [Cybersecurity Stocks Rally While Large-Cap Tech Slides: CrowdStrike, Palo Alto, Okta, and Palantir Each Gain 4%](https://247wallst.com/investing/2026/09/23/cybersecurity-stocks-rally-while-large-cap-tech-slides-crowdstrike-palo-alto-okta-and-palantir-each-gain-4/).<br>
<a id="ref-5"></a>[5] The Motley Fool (2026-09-20). [Why CrowdStrike, Palo Alto Networks, SentinelOne, and Other Cybersecurity Stocks Surged This Week](https://www.fool.com/investing/2026/09/20/why-crowdstrike-palo-alto-sentinelone-stocks-up/).<br>
<a id="ref-6"></a>[6] Yahoo Finance (2026). [Cloudflare Stock Jumped 10% on an OpenAI Security Launch](https://finance.yahoo.com/markets/stocks/articles/cloudflare-stock-jumped-10-openai-085051388.html).

---

## Appendix A. Terminology

- **ARR**: Annual Recurring Revenue. 구독 계약에서 해마다 반복해 들어오는 매출.
- **block trade**: 기관이 장 밖에서 한 번에 주고받는 대량 거래.
- **endpoint**: 보안 영역에서 PC·server 같은 단말.
- **거래량 배수**: 최근 21 거래일 평균 거래량을 그 앞 63 거래일 평균 거래량으로 나눈 값.

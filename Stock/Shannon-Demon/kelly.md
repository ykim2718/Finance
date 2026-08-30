# Kelly Criterion

Rev. 0 | Created: 2026-08-30 | Updated: 2026-08-30 05:45 UTC

> **Goal** — 베팅 비중 하나가 장기 성장률을 얼마나 좌우하는지 수치로 확정한다. "적당히 걸어라" 가 아니라 "최적 비중이 얼마이고, 거기서 벗어나면 성장률과 손실 확률이 각각 얼마나 나빠지는가" 를 판단 기준으로 쓸 수 있게 한다.
>
> **Non-Goals** — 승률과 배당률의 추정은 다루지 않는다. 이 문서는 그 값들이 정확히 주어졌다고 보고 비중만 푼다. 자산 2개 이상의 동시 배분, 추정 오차가 있을 때의 축소 규칙, 세금과 거래비용도 범위 밖이다.
>
> **Background** — 유리한 베팅을 찾는 것과 얼마를 걸지 정하는 것은 다른 문제이다. 기대값이 양수인 베팅도 크게 걸면 장기 성장률이 0 이나 음수가 된다. John Kelly 는 1956년에 이 문제를 기대 log 자산의 최대화로 정식화했다 \[[1](#ref-1)\]. 이 문서는 두 결과만 있는 단순한 베팅에서 그 해를 닫힌 형태로 구하고, 수치 최적화와 Monte Carlo 로 각각 교차 검증한다.

## 1. Pipeline

`kelly.py` 는 같은 질문에 세 가지 방법으로 답한 뒤 서로 맞는지 확인한다. 세 답이 어긋나면 실행을 중단한다.

```text
bet parameters (u, d, c, p)
        |
        +--> closed form      -> f* exactly
        |
        +--> numeric search   -> f* by scipy minimize_scalar   --+
        |                                                        +--> agreement check
        +--> growth curve     -> g(f) on a grid                  |
        |                                                        |
        +--> Monte Carlo      -> terminal log growth samples   --+
```

- Closed form — 성장 함수를 미분해 0 으로 놓고 푼 해. 계산 비용이 없고 정확하다.
- Numeric search — 같은 함수를 `scipy.optimize.minimize_scalar` 로 최대화한 해. 닫힌 해의 유도가 맞는지 확인하는 용도이다.
- Growth curve — 비중 격자 위에서 계산한 성장률 곡선. 최적점 주변의 모양을 본다.
- Monte Carlo — 실제로 게임을 반복해 얻은 성장률 표본. 해석해가 현실의 경로 분포와 맞는지 확인한다.

## 2. Method

### 2.1 The bet

한 기간에 결과가 둘뿐인 베팅을 둔다. 자산의 비중 $f$ 를 위험 자산에 걸고 나머지 $1-f$ 는 현금으로 둔다. 위험 자산은 확률 $p$ 로 $u$ 배, 확률 $1-p$ 로 $d$ 배가 되고 현금은 $c$ 배가 된다.

한 기간이 지난 뒤 자산의 배수는 두 값 중 하나이다.

$$W_{\text{up}} = f u + (1-f) c, \qquad W_{\text{down}} = f d + (1-f) c$$

베팅이 성립하려면 $d \lt c \lt u$ 여야 한다. 현금이 두 결과 밖에 있으면 한쪽이 지배해 고를 것이 없어지므로, `BetSpec` 은 이 조건을 어기는 입력을 에러로 막는다.

### 2.2 Closed-form optimum

장기 성장률을 결정하는 것은 산술평균이 아니라 기대 log 성장률이다.

$$g(f) = p \ln W_{\text{up}} + (1-p) \ln W_{\text{down}}$$

$A = u - c$, $B = d - c$ 로 두면 $g'(f) = 0$ 은 일차식이 되어 해가 하나로 떨어진다.

$$f^{*} = -\frac{c \left(p A + (1-p) B\right)}{A B}$$

분자의 $p A + (1-p) B$ 는 현금 대비 초과 수익의 기댓값이고, 분모의 $A B$ 는 음수이다. 따라서 기대 초과 수익이 양수일 때만 $f^{*}$ 가 양수가 된다.

### 2.3 Domain and the ruin fraction

$f$ 를 무한정 키울 수 없다. 하락이 한 번 나왔을 때 자산이 0 이하가 되는 비중이 존재하기 때문이다.

$$f_{\text{ruin}} = \frac{c}{c - d}$$

$f \ge f_{\text{ruin}}$ 이면 $W_{\text{down}} \le 0$ 이 되어 log 가 정의되지 않는다. 격자와 수치 최적화의 정의역을 모두 이 값 아래로 제한하며, `--max-fraction` 이 이 값에 닿으면 에러를 낸다. 정의역 밖을 조용히 잘라내면 사용자는 자기가 지정한 구간이 그대로 쓰인 줄 알게 된다.

### 2.4 Cross-check between the three answers

닫힌 해와 수치 해의 차이가 허용치를 넘으면 `RuntimeError` 로 실행을 중단한다. 성장 함수를 잘못 적었거나 최적화 구간을 잘못 잡았을 때 결과가 조용히 틀린 채로 남는 것을 막기 위함이다.

Monte Carlo 는 각 비중마다 게임을 `--n-periods` 기간 반복해 최종 자산을 얻고, 그 log 를 기간 수로 나누어 기간당 성장률 표본을 만든다. 이 표본의 중앙값이 해석해와 맞아야 한다. 평균이 아니라 중앙값을 쓰는 이유는, 자산의 분포가 log 정규에 가까워 평균이 소수의 극단 경로에 끌려가기 때문이다.

## 3. Input

외부 자료를 읽지 않는다. 모든 입력은 CLI option 이며, 난수는 seed 가 고정된 generator 에서 나온다. 같은 seed 와 같은 option 이면 결과가 재현된다.

Table 1. Bet and simulation parameters of this run
| Parameter | Value | Meaning |
|---|---|---|
| `--up-factor` | 2.0 | 상승 시 위험 자산 배수 |
| `--down-factor` | 0.5 | 하락 시 위험 자산 배수 |
| `--cash-factor` | 1.0 | 현금 배수 |
| `--up-prob` | 0.5 | 상승 확률 |
| `--max-fraction` | 1.0 | 성장 곡선 격자의 최대 비중 |
| `--grid-points` | 401 | 격자점 수 |
| `--sim-fractions` | 0.10 0.25 0.50 0.75 1.00 | Monte Carlo 대상 비중 |
| `--n-periods` | 100 | 경로당 기간 수 |
| `--n-paths` | 20,000 | 비중당 경로 수 |
| `--seed` | 20260829 | 난수 seed |

이 parameter 에서 위험 자산 단독의 기하평균은 $\sqrt{u d} = 1$ 이므로, 자산 자체의 장기 성장률은 0 이다. 성장은 오직 비중 선택에서 나온다.

`kelly.py` 는 같은 folder 의 `shannon_demon.py` 에서 simulator 를 가져와 Monte Carlo 를 돌린다. 두 파일이 같은 folder 에 있어야 실행된다.

## 4. Output

산출물은 `--output-folder` 아래 script 이름 folder 로 들어간다. 이 문서가 인용하는 실행은 `Shannons_Demon_fig` 를 root 로 썼다.

```text
Shannons_Demon_fig/
└── kelly/
    ├── growth_curve.csv
    ├── simulated_log_growth.csv
    ├── growth_curve.png
    └── growth_violin.png
```

- `growth_curve.csv` — 1 file, shape (401 × 3). 1 row = 1 fraction on the grid.
- `simulated_log_growth.csv` — 1 file, shape (100,000 × 3). 1 row = 1 path × 1 fraction.
- `growth_curve.png` — 1 file.
- `growth_violin.png` — 1 file.

분포를 그리는 figure 는 요약값이 아니라 표본을 저장한다. 이 문서의 모든 수치는 위 두 csv 에서 계산했으며 figure 에서 눈으로 읽은 값이 아니다.

## 5. Result

### 5.1 The optimum

닫힌 해는 0.500000, 수치 해도 0.500000 이며 둘의 차이는 3.33e-16 이다. 그 지점의 기대 log 성장률은 +0.058892, 기간당 수익률로는 +6.0660% 이다. 401개 격자점 중 최대값을 주는 점도 0.5000 이다.

### 5.2 Growth by fraction

Table 2. Growth rate and simulated outcome by fraction, from `growth_curve.csv` and `simulated_log_growth.csv`
| Fraction | Analytic log growth | Return per period | Share of maximum | Simulated median | 5th percentile | 95th percentile | Loss probability |
|---|---|---|---|---|---|---|---|
| 0.100 | +0.022008 | +2.2252% | 0.3737 | +0.022008 | +0.0103 | +0.0337 | 0.00085 |
| 0.250 | +0.044806 | +4.5825% | 0.7608 | +0.044806 | +0.0163 | +0.0733 | 0.00665 |
| 0.375 | +0.055407 | +5.6971% | 0.9408 | — | — | — | — |
| 0.500 | +0.058892 | +6.0660% | 1.0000 | +0.058892 | +0.0034 | +0.1143 | 0.04320 |
| 0.625 | +0.055407 | +5.6971% | 0.9408 | — | — | — | — |
| 0.750 | +0.044806 | +4.5825% | 0.7608 | +0.044806 | -0.0376 | +0.1272 | 0.18680 |
| 1.000 | +0.000000 | +0.0000% | 0.0000 | +0.000000 | -0.1109 | +0.1109 | 0.45305 |

0.375 와 0.625 는 격자에만 있고 Monte Carlo 대상이 아니므로 뒤 네 열을 `—` 로 둔다. 시뮬레이션 중앙값은 대상 비중 네 곳 모두에서 해석해와 소수점 여섯 자리까지 일치한다.

곡선은 $f^{*}$ 를 축으로 대칭이다. 0.250 과 0.750 의 성장률이 +0.044806 로 같고, 0.375 와 0.625 도 +0.055407 로 같다. 손실 확률은 대칭이 아니다. 같은 성장률을 주는 0.250 에서 0.00665, 0.750 에서 0.18680 이다.

<img src="Shannons_Demon_fig/kelly/growth_curve.png" width="900" style="max-width: 100%;" alt="Fig 1">
Fig 1. Expected log growth against bet size, with the simulated medians overlaid, from `kelly.py`

### 5.3 Simulated distribution

<img src="Shannons_Demon_fig/kelly/growth_violin.png" width="900" style="max-width: 100%;" alt="Fig 2">
Fig 2. Simulated growth distribution by bet size, from `kelly.py`

비중이 커질수록 분포의 폭이 넓어진다. 5th percentile 과 95th percentile 의 간격은 0.100 에서 0.0235, 0.500 에서 0.1109, 1.000 에서 0.2218 이다. 5th percentile 의 부호는 0.500 까지 양수이고 0.750 부터 음수이다.

## 6. Analysis

### 6.1 The curve is flat at the top and steep at the edge

최적점 주변이 평평하다는 것이 Table 2 의 가장 실용적인 부분이다. 비중을 0.375 나 0.625 로 잡아도 성장률은 최대값의 0.9408 배로, 25% 를 잘못 잡고도 6% 만 잃는다. 승률과 배당률을 정확히 알 수 없는 실제 상황에서 이 평평함은 여유를 뜻한다.

반대로 가장자리는 가파르다. 비중 1.000 에서 성장률은 정확히 0 이 된다. 기대값이 양수인 베팅에 전 재산을 걸면 장기적으로 제자리라는 뜻이며, 이 게임에서는 그 지점이 파산 비중 2.0 의 절반에 불과하다.

### 6.2 Overbetting and underbetting cost the same growth but not the same risk

5.2 절의 대칭이 오해를 부르기 쉽다. 성장률만 보면 $f^{*}$ 에서 같은 거리만큼 적게 거는 것과 많이 거는 것이 동등해 보인다. 그러나 손실 확률은 0.250 에서 0.00665, 0.750 에서 0.18680 으로 28배 차이가 난다.

이유는 두 방향이 다른 것을 바꾸기 때문이다. 적게 걸면 분포 전체가 좁아지고, 많이 걸면 분포가 넓어진 채로 중앙값만 내려온다. 성장률이라는 한 숫자는 이 차이를 담지 못한다. 추정에 자신이 없을 때 절반만 거는 half Kelly 관행 \[[2](#ref-2)\] 이 합리적인 것은 성장률을 0.7608 배로 줄이는 대가로 손실 확률을 0.04320 에서 0.00665 로 낮추기 때문이다.

### 6.3 Why the three methods must agree

세 방법이 일치한다는 것 자체가 결과이다. 닫힌 해와 수치 해가 3.33e-16 안에서 만난 것은 2.2 절의 미분이 맞다는 뜻이고, Monte Carlo 중앙값이 해석해와 여섯 자리까지 맞은 것은 기대 log 성장률이 실제 경로의 중앙 성장률이라는 해석이 맞다는 뜻이다.

두 번째가 특히 중요하다. 기대 log 성장률은 정의상 log 자산의 기댓값이지 흔한 결과가 아니다. 그런데도 중앙값과 일치하는 것은, 기간이 길어질수록 log 자산이 정규분포에 가까워져 평균과 중앙값이 같아지기 때문이다. 기간이 짧으면 이 일치는 깨진다.

### 6.4 Limits and next steps

- 결과가 둘뿐인 베팅. 실제 자산의 수익률은 연속 분포이며, 그 경우 최적 비중은 다른 형태를 갖는다.
- $p$, $u$, $d$ 가 정확히 알려졌다는 가정. 실제로는 추정값이며, 추정 오차는 최적 비중을 과대평가하는 쪽으로 작용한다.
- 자산 하나와 현금. 여러 자산을 동시에 굴릴 때는 자산 간 correlation 이 들어와 비중이 벡터가 된다.
- 기간당 결과가 독립이라는 가정. 추세나 평균회귀가 있으면 이 해는 최적이 아니다.

다음 단계로는 $p$ 에 추정 오차를 주고 성장률이 얼마나 무너지는지 보는 것이 가장 값이 크다. 6.1 절의 평평함이 그 오차를 얼마나 흡수하는지가 실전에서 비중을 정하는 근거가 된다.

## References

<a id="ref-1"></a>
[1] Kelly, J. L. Jr. "A New Interpretation of Information Rate." Bell System Technical Journal 35, no. 4 (1956): 917–926. DOI 10.1002/j.1538-7305.1956.tb03809.x

<a id="ref-2"></a>
[2] Thorp, E. O. "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market." In Handbook of Asset and Liability Management, Volume 1, 385–428. North-Holland, 2006. DOI 10.1016/S1872-0978(06)01009-X

---

## Appendix A. Terminology

- **closed form** — 반복 계산 없이 식 하나로 값을 주는 해.
- **half Kelly** — 최적 비중의 절반만 거는 관행.
- **Kelly criterion** — 기대 log 자산을 최대화하는 베팅 비중을 구하는 규칙.
- **log growth** — 자산 배수의 자연로그. 복리로 더해지므로 장기 성장률의 단위가 된다.
- **Monte Carlo** — 난수로 경로를 여러 번 생성해 분포를 추정하는 방법.
- **overbetting** — 최적 비중보다 크게 거는 것.
- **ruin fraction** — 한 번의 하락으로 자산이 0 이하가 되는 최소 비중.
- **underbetting** — 최적 비중보다 작게 거는 것.

## Appendix B. CLI (Command Line Options)

Option 없이 실행하면 script 이름과 version 을 출력한다. `-h` 로 전체 목록을, `-v` 로 version 을 본다. `--output-folder` 는 필수이며 모든 산출물의 root 가 된다. 아래 명령은 이 문서가 있는 folder 를 기준으로 한다.

```bash
python3 src/kelly.py --output-folder Shannons_Demon_fig
python3 src/kelly.py --output-folder Shannons_Demon_fig --up-prob 0.55 --sim-fractions 0.1 0.2 0.3
```

Table 3. CLI options of `kelly.py`
| Option | Type | Default | Required | Description |
|---|---|---|---|---|
| `--output-folder` | path | — | yes | 산출물 root |
| `--up-factor` | float | 2.0 | no | 상승 시 위험 자산 배수 |
| `--down-factor` | float | 0.5 | no | 하락 시 위험 자산 배수 |
| `--cash-factor` | float | 1.0 | no | 현금 배수 |
| `--up-prob` | float | 0.5 | no | 상승 확률 |
| `--max-fraction` | float | 1.0 | no | 성장 곡선 격자의 최대 비중 |
| `--grid-points` | int | 401 | no | 격자점 수 |
| `--sim-fractions` | float list | 0.10 0.25 0.50 0.75 1.00 | no | Monte Carlo 대상 비중 |
| `--n-periods` | int | 100 | no | 경로당 기간 수 |
| `--n-paths` | int | 20000 | no | 비중당 경로 수 |
| `--chunk-size` | int | 4000 | no | 한 번에 계산할 경로 수 |
| `--seed` | int | 20260829 | no | 난수 seed |

# FedAvg vs CosAvg vs CCRA

Final accuracy (%), mean of last 5 rounds:

| Scenario | FedAvg | CosAvg (base paper) | CCRA (ours) | CCRA w/o channel context |
|---|---|---|---|---|
| No attack, ideal channel | 46.51 | 47.15 | 44.49 | - |
| No attack, EW-jammed lossy channel | 44.58 | 45.60 | 43.06 | - |
| 30% label-flip, ideal channel | 37.63 | 36.58 | 43.26 | - |
| 30% label-flip + EW-jammed lossy channel | 36.78 | 39.70 | 42.98 | 42.20 |

Average weight given to malicious drones (last 10 rounds):

- 30% label-flip, ideal channel / FedAvg: 0.260
- 30% label-flip, ideal channel / CosAvg (base paper): 0.191
- 30% label-flip, ideal channel / CCRA (ours): 0.019
- 30% label-flip + EW-jammed lossy channel / FedAvg: 0.275
- 30% label-flip + EW-jammed lossy channel / CosAvg (base paper): 0.215
- 30% label-flip + EW-jammed lossy channel / CCRA (ours): 0.084
- 30% label-flip + EW-jammed lossy channel / CCRA w/o channel context: 0.084

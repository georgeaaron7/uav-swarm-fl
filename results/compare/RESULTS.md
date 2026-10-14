# FedAvg vs CosAvg vs CCRA

Final accuracy (%), mean of last 5 rounds:

| Scenario | FedAvg | CosAvg (base paper) | CCRA (ours) | CCRA w/o channel context |
|---|---|---|---|---|
| 30% label-flip + EW-jammed lossy channel | 36.78 | 39.70 | 42.98 | 42.20 |

Average weight given to malicious drones (last 10 rounds):

- 30% label-flip + EW-jammed lossy channel / FedAvg: 0.275
- 30% label-flip + EW-jammed lossy channel / CosAvg (base paper): 0.215
- 30% label-flip + EW-jammed lossy channel / CCRA (ours): 0.084
- 30% label-flip + EW-jammed lossy channel / CCRA w/o channel context: 0.084

# Multi-seed benchmark summary

Accuracy is reported as mean ± sample standard deviation across non-diverged seeds; divergence is reported separately and is never silently imputed.

| Scenario | Aggregator | Successful/total | Diverged | Final accuracy | PDR | Latency (s) | Handovers |
|---|---|---:|---:|---:|---:|---:|---:|
| alie_hfl_lossy | ccra | 3/3 | 0 | 37.90 ± 1.09 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | ccra_noctx | 3/3 | 0 | 38.04 ± 2.43 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | cosavg | 3/3 | 0 | 36.64 ± 1.72 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | fedavg | 3/3 | 0 | 35.45 ± 0.71 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | fltrust | 3/3 | 0 | 15.75 ± 5.84 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | median | 3/3 | 0 | 20.66 ± 0.08 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | multi_krum | 3/3 | 0 | 18.34 ± 4.65 | 0.834 | 0.205 | 14.0 |
| alie_hfl_lossy | trimmed_mean | 3/3 | 0 | 32.75 ± 3.00 | 0.834 | 0.205 | 14.0 |
| alie_hfl_trace | ccra | 3/3 | 0 | 43.20 ± 2.35 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | ccra_noctx | 3/3 | 0 | 41.32 ± 4.58 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | cosavg | 3/3 | 0 | 37.60 ± 1.81 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | fedavg | 3/3 | 0 | 36.48 ± 2.46 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | fltrust | 3/3 | 0 | 16.14 ± 4.87 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | median | 3/3 | 0 | 24.60 ± 6.91 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | multi_krum | 3/3 | 0 | 23.86 ± 6.73 | 0.939 | 0.071 | 1.0 |
| alie_hfl_trace | trimmed_mean | 3/3 | 0 | 31.00 ± 2.96 | 0.939 | 0.071 | 1.0 |
| alie_ideal | ccra | 3/3 | 0 | 44.02 ± 1.68 | 1.000 | 0.000 | 0.0 |
| alie_ideal | ccra_noctx | 3/3 | 0 | 43.10 ± 2.15 | 1.000 | 0.000 | 0.0 |
| alie_ideal | cosavg | 3/3 | 0 | 31.65 ± 5.35 | 1.000 | 0.000 | 0.0 |
| alie_ideal | fedavg | 3/3 | 0 | 33.47 ± 1.86 | 1.000 | 0.000 | 0.0 |
| alie_ideal | fltrust | 3/3 | 0 | 18.65 ± 3.12 | 1.000 | 0.000 | 0.0 |
| alie_ideal | median | 3/3 | 0 | 15.37 ± 2.45 | 1.000 | 0.000 | 0.0 |
| alie_ideal | multi_krum | 3/3 | 0 | 23.06 ± 13.84 | 1.000 | 0.000 | 0.0 |
| alie_ideal | trimmed_mean | 3/3 | 0 | 20.58 ± 3.52 | 1.000 | 0.000 | 0.0 |
| clean_hfl_lossy | ccra | 3/3 | 0 | 43.74 ± 1.54 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | ccra_noctx | 3/3 | 0 | 41.88 ± 2.60 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | cosavg | 3/3 | 0 | 43.61 ± 1.91 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | fedavg | 3/3 | 0 | 43.48 ± 1.88 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | fltrust | 3/3 | 0 | 19.53 ± 0.20 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | median | 3/3 | 0 | 39.52 ± 0.32 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | multi_krum | 3/3 | 0 | 38.55 ± 5.47 | 0.834 | 0.205 | 14.0 |
| clean_hfl_lossy | trimmed_mean | 3/3 | 0 | 43.47 ± 0.56 | 0.834 | 0.205 | 14.0 |
| clean_hfl_trace | ccra | 3/3 | 0 | 44.98 ± 1.08 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | ccra_noctx | 3/3 | 0 | 43.69 ± 1.92 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | cosavg | 3/3 | 0 | 43.82 ± 2.96 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | fedavg | 3/3 | 0 | 45.33 ± 0.60 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | fltrust | 3/3 | 0 | 19.66 ± 1.98 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | median | 3/3 | 0 | 40.98 ± 0.14 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | multi_krum | 3/3 | 0 | 38.81 ± 2.65 | 0.939 | 0.071 | 1.0 |
| clean_hfl_trace | trimmed_mean | 3/3 | 0 | 44.00 ± 0.52 | 0.939 | 0.071 | 1.0 |
| clean_ideal | ccra | 3/3 | 0 | 45.15 ± 0.92 | 1.000 | 0.000 | 0.0 |
| clean_ideal | ccra_noctx | 3/3 | 0 | 44.54 ± 1.30 | 1.000 | 0.000 | 0.0 |
| clean_ideal | cosavg | 3/3 | 0 | 44.42 ± 3.15 | 1.000 | 0.000 | 0.0 |
| clean_ideal | fedavg | 3/3 | 0 | 46.08 ± 0.50 | 1.000 | 0.000 | 0.0 |
| clean_ideal | fltrust | 3/3 | 0 | 19.72 ± 2.48 | 1.000 | 0.000 | 0.0 |
| clean_ideal | median | 3/3 | 0 | 39.71 ± 0.77 | 1.000 | 0.000 | 0.0 |
| clean_ideal | multi_krum | 3/3 | 0 | 38.24 ± 2.04 | 1.000 | 0.000 | 0.0 |
| clean_ideal | trimmed_mean | 3/3 | 0 | 43.40 ± 0.29 | 1.000 | 0.000 | 0.0 |
| gaussian_hfl_lossy | ccra | 3/3 | 0 | 40.02 ± 1.76 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | ccra_noctx | 3/3 | 0 | 38.64 ± 2.80 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | cosavg | 3/3 | 0 | 35.28 ± 1.39 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | fedavg | 3/3 | 0 | 38.21 ± 1.65 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | fltrust | 3/3 | 0 | 17.08 ± 4.36 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | median | 3/3 | 0 | 29.75 ± 3.28 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | multi_krum | 3/3 | 0 | 37.38 ± 0.72 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_lossy | trimmed_mean | 3/3 | 0 | 37.92 ± 1.19 | 0.834 | 0.205 | 14.0 |
| gaussian_hfl_trace | ccra | 3/3 | 0 | 43.51 ± 2.98 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | ccra_noctx | 3/3 | 0 | 42.51 ± 3.89 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | cosavg | 3/3 | 0 | 36.84 ± 1.66 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | fedavg | 3/3 | 0 | 40.45 ± 1.79 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | fltrust | 3/3 | 0 | 16.63 ± 4.29 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | median | 3/3 | 0 | 34.24 ± 1.28 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | multi_krum | 3/3 | 0 | 40.27 ± 1.68 | 0.939 | 0.071 | 1.0 |
| gaussian_hfl_trace | trimmed_mean | 3/3 | 0 | 39.35 ± 2.05 | 0.939 | 0.071 | 1.0 |
| gaussian_ideal | ccra | 3/3 | 0 | 43.92 ± 2.71 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | ccra_noctx | 3/3 | 0 | 43.44 ± 3.10 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | cosavg | 3/3 | 0 | 36.36 ± 2.75 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | fedavg | 3/3 | 0 | 40.96 ± 1.64 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | fltrust | 3/3 | 0 | 18.69 ± 3.14 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | median | 3/3 | 0 | 36.04 ± 2.89 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | multi_krum | 3/3 | 0 | 40.79 ± 3.70 | 1.000 | 0.000 | 0.0 |
| gaussian_ideal | trimmed_mean | 3/3 | 0 | 39.09 ± 2.00 | 1.000 | 0.000 | 0.0 |
| ipm_hfl_lossy | ccra | 3/3 | 0 | 37.60 ± 2.34 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | ccra_noctx | 3/3 | 0 | 36.36 ± 3.27 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | cosavg | 3/3 | 0 | 39.08 ± 1.16 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | fedavg | 3/3 | 0 | 36.23 ± 1.94 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | fltrust | 3/3 | 0 | 15.56 ± 5.42 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | median | 3/3 | 0 | 18.29 ± 2.44 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_lossy | multi_krum | 0/3 | 3 | — | nan | nan | nan |
| ipm_hfl_lossy | trimmed_mean | 3/3 | 0 | 33.60 ± 1.27 | 0.834 | 0.205 | 14.0 |
| ipm_hfl_trace | ccra | 3/3 | 0 | 42.28 ± 2.42 | 0.939 | 0.071 | 1.0 |
| ipm_hfl_trace | ccra_noctx | 3/3 | 0 | 41.20 ± 4.03 | 0.939 | 0.071 | 1.0 |
| ipm_hfl_trace | cosavg | 1/3 | 2 | 47.05 ± 0.00 | 0.925 | 0.074 | 1.0 |
| ipm_hfl_trace | fedavg | 3/3 | 0 | 38.74 ± 2.11 | 0.939 | 0.071 | 1.0 |
| ipm_hfl_trace | fltrust | 3/3 | 0 | 16.64 ± 4.55 | 0.939 | 0.071 | 1.0 |
| ipm_hfl_trace | median | 1/3 | 2 | 19.21 ± 0.00 | 0.925 | 0.074 | 1.0 |
| ipm_hfl_trace | multi_krum | 1/3 | 2 | 9.94 ± 0.00 | 0.925 | 0.074 | 1.0 |
| ipm_hfl_trace | trimmed_mean | 3/3 | 0 | 34.15 ± 2.85 | 0.939 | 0.071 | 1.0 |
| ipm_ideal | ccra | 3/3 | 0 | 43.88 ± 1.69 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | ccra_noctx | 3/3 | 0 | 43.41 ± 1.57 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | cosavg | 3/3 | 0 | 44.29 ± 2.70 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | fedavg | 3/3 | 0 | 39.32 ± 1.76 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | fltrust | 3/3 | 0 | 18.65 ± 3.12 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | median | 3/3 | 0 | 18.95 ± 3.34 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | multi_krum | 3/3 | 0 | 10.02 ± 0.03 | 1.000 | 0.000 | 0.0 |
| ipm_ideal | trimmed_mean | 3/3 | 0 | 28.16 ± 2.28 | 1.000 | 0.000 | 0.0 |
| label_flip_hfl_lossy | ccra | 3/3 | 0 | 38.92 ± 4.59 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | ccra_noctx | 3/3 | 0 | 38.05 ± 1.48 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | cosavg | 3/3 | 0 | 28.56 ± 3.57 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | fedavg | 3/3 | 0 | 34.53 ± 2.30 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | fltrust | 3/3 | 0 | 15.30 ± 4.44 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | median | 3/3 | 0 | 30.40 ± 2.70 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | multi_krum | 3/3 | 0 | 27.57 ± 10.05 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_lossy | trimmed_mean | 3/3 | 0 | 35.20 ± 2.89 | 0.834 | 0.205 | 14.0 |
| label_flip_hfl_trace | ccra | 3/3 | 0 | 42.50 ± 3.28 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | ccra_noctx | 3/3 | 0 | 42.08 ± 3.06 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | cosavg | 3/3 | 0 | 31.13 ± 6.30 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | fedavg | 3/3 | 0 | 37.09 ± 1.90 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | fltrust | 3/3 | 0 | 16.04 ± 4.84 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | median | 3/3 | 0 | 33.84 ± 2.36 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | multi_krum | 3/3 | 0 | 40.73 ± 1.53 | 0.939 | 0.071 | 1.0 |
| label_flip_hfl_trace | trimmed_mean | 3/3 | 0 | 35.52 ± 2.44 | 0.939 | 0.071 | 1.0 |
| label_flip_ideal | ccra | 3/3 | 0 | 43.88 ± 2.08 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | ccra_noctx | 3/3 | 0 | 42.12 ± 1.77 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | cosavg | 3/3 | 0 | 30.06 ± 11.39 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | fedavg | 3/3 | 0 | 38.66 ± 1.12 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | fltrust | 3/3 | 0 | 16.81 ± 4.45 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | median | 3/3 | 0 | 32.50 ± 3.34 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | multi_krum | 3/3 | 0 | 40.19 ± 3.82 | 1.000 | 0.000 | 0.0 |
| label_flip_ideal | trimmed_mean | 3/3 | 0 | 35.25 ± 1.85 | 1.000 | 0.000 | 0.0 |
| sign_flip_hfl_lossy | ccra | 3/3 | 0 | 39.13 ± 2.37 | 0.834 | 0.205 | 14.0 |
| sign_flip_hfl_lossy | ccra_noctx | 3/3 | 0 | 37.39 ± 0.47 | 0.834 | 0.205 | 14.0 |
| sign_flip_hfl_lossy | cosavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_lossy | fedavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_lossy | fltrust | 3/3 | 0 | 15.72 ± 5.73 | 0.834 | 0.205 | 14.0 |
| sign_flip_hfl_lossy | median | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_lossy | multi_krum | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_lossy | trimmed_mean | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_trace | ccra | 2/3 | 1 | 42.60 ± 3.15 | 0.939 | 0.070 | 1.0 |
| sign_flip_hfl_trace | ccra_noctx | 3/3 | 0 | 42.93 ± 2.45 | 0.939 | 0.071 | 1.0 |
| sign_flip_hfl_trace | cosavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_trace | fedavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_hfl_trace | fltrust | 3/3 | 0 | 16.31 ± 4.80 | 0.939 | 0.071 | 1.0 |
| sign_flip_hfl_trace | median | 1/3 | 2 | 24.71 ± 0.00 | 0.925 | 0.074 | 1.0 |
| sign_flip_hfl_trace | multi_krum | 1/3 | 2 | 38.47 ± 0.00 | 0.925 | 0.074 | 1.0 |
| sign_flip_hfl_trace | trimmed_mean | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_ideal | ccra | 3/3 | 0 | 43.68 ± 2.13 | 1.000 | 0.000 | 0.0 |
| sign_flip_ideal | ccra_noctx | 3/3 | 0 | 43.12 ± 2.62 | 1.000 | 0.000 | 0.0 |
| sign_flip_ideal | cosavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_ideal | fedavg | 0/3 | 3 | — | nan | nan | nan |
| sign_flip_ideal | fltrust | 3/3 | 0 | 18.36 ± 3.84 | 1.000 | 0.000 | 0.0 |
| sign_flip_ideal | median | 3/3 | 0 | 26.61 ± 3.98 | 1.000 | 0.000 | 0.0 |
| sign_flip_ideal | multi_krum | 3/3 | 0 | 40.79 ± 3.70 | 1.000 | 0.000 | 0.0 |
| sign_flip_ideal | trimmed_mean | 0/3 | 3 | — | nan | nan | nan |

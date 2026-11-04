# SwarmCompute
<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
React, TypeScript, Vite, Tailwind, Recharts; compiled assets served by FastAPI on one port. Specified in the implementation brief. User selected code-first construction.

## Users
Researchers coordinating a UAV federated-learning study, and voluntary laptop owners contributing independent NVIDIA GPU experiments.

## Product Purpose
Execute and monitor independent experiments across reachable LAN or Tailscale machines, preserving the simulator's scientific design, histories and provenance.

## Operating Context
A stable self-hosted coordinator and 3–8 heterogeneous Windows/Linux GPU laptops. Owners may pause or disconnect. Researchers need to tell numerical divergence from infrastructure failure.

## Capabilities and Constraints
Use actual coordinator state only. No fabricated runs, throughput, sensors or ETA. Physical workers are distinct from virtual UAV clients. Preserve historical results and existing analysis formats. No generic shell execution, mandatory cloud services or automatic driver/sleep changes.

## Evidence on Hand
Existing simulator, experiment planner, scientific validation and historical results. Upstream main now supplies bp_fresh and bp_reuse; they are integrated as a separate comparison, with checkpointed reuse state. Hardware acceptance on two physical NVIDIA laptops remains an external validation requirement.

## Product Principles
Keep scientific outcomes explicit. Make recovery inspectable. Respect owner control. Prefer maintainable infrastructure and clear, dense monitoring information.

## Brand Commitments
SwarmCompute. Useful, responsive, dark-compatible operations console; user approved building directly in code.

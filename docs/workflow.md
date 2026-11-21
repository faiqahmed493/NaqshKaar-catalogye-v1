# Workflow and states

Three readiness concepts stay separate (SRS §3): a variant can be **eligible** (catalogue admission), its 3D asset
can be **qualified** (scale and look checked), and only the planner decides whether a layout is **verified**.
None implies another.

## Variant (catalogue admission)

```mermaid
stateDiagram-v2
  state "In review" as InReview
  state "In catalogue" as Eligible
  [*] --> Draft
  Draft --> InReview : curator submits
  InReview --> Eligible : approve, all required conditions pass
  InReview --> Ineligible : reject
  InReview --> Draft : request changes
  Ineligible --> InReview : corrected and resubmitted
  Eligible --> Reassessing : price/stock now fails a condition, link mismatch, dims or sale unit changed
  Reassessing --> Eligible : approve again
  Eligible --> Retired : retire
```

Admission conditions (all required unless marked advisory): identifiable variant · supported category ·
intended room use · PKR price recorded · unambiguous sale unit · assembled source-backed W × D × H ·
reviewed image of this variant · purchase link checked and matching · dated source evidence · not known
to be unorderable · set contents for sets · *(advisory)* set component dimensions · *(advisory)* recent price.

## Generation job

```mermaid
stateDiagram-v2
  [*] --> Queued
  Queued --> Claimed : worker claims (SKIP LOCKED)
  Claimed --> Running : first progress report
  Running --> Uploaded : GLB uploaded
  Uploaded --> Postprocessing : CPU worker picks up the asset
  Postprocessing --> Succeeded : checks recorded
  Running --> Queued : error or lost heartbeat, attempts left
  Running --> Failed : error, no attempts left
  Queued --> Cancelled : user
  Running --> Cancelled : user (worker stops at next step)
```

## 3D asset

```mermaid
stateDiagram-v2
  state "Checking" as Processing
  state "Awaiting review" as InReview
  state "Needs correction" as NeedsCorrection
  [*] --> Processing : generated or uploaded
  Processing --> InReview : all automated checks pass
  Processing --> NeedsCorrection : a required check fails
  NeedsCorrection --> Processing : turn and re-run, or new dims
  InReview --> Processing : turn and re-run
  InReview --> Qualified : reviewer approves (6-point checklist)
  InReview --> NeedsCorrection : reviewer
  InReview --> Rejected : reviewer
  NeedsCorrection --> Rejected : corrected version uploaded
  Qualified --> Stale : variant dimensions revised
```

Automated checks: file opens · finite coordinates · non-degenerate extents · recorded W × D × H available ·
width / depth / height within max(5 mm, 1 %) · proportions (warn above ×1.15, fail above ×1.5) · exported GLB
re-opens · textures embedded · Khronos glTF validator · triangle budget (warning). Then the person-only
**visual review**.

Only one qualified asset per variant is *selected* (served to the planner). The planner gets `asset_ready = true`
only when that asset was qualified against the variant's **current** dimension revision.

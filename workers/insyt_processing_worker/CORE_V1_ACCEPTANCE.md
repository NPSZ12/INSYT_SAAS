# INSYT Shared Ingestion Core v1

Validated September 27, 2026.

The ingestion spine is shared by Capture and Discovery.

Workspace behavior may diverge only after the common ingestion handoff.

## Protected Spine

Upload
→ Inventory
→ Container / Workbook Expansion
→ Hash
→ deNIST
→ Dedupe
→ Prior Processed
→ Family / Provenance
→ File Routing / Train Station
→ Processing Sets
→ INSYT Doc ID
→ Text / OCR Preparation
→ Detection Ready

## Capture Regression

### PDF
PASS

Requirements:
- 1 source upload
- 1 expanded leaf
- Processing Set created
- Doc ID assigned
- Text Extraction completes
- OCR Preflight reached
- job completes with 0 exceptions

### XLSX
PASS

Requirements:
- workbook expands into worksheet CSV children
- known CSV children route core
- duplicates are excluded correctly
- eligible sheets receive Processing Set membership
- Doc IDs assigned
- text extraction completes
- structured documents become Detection Ready
- final duplicate/unique totals remain authoritative

### Unknown Extension
PASS

Requirements:
- inventory succeeds
- hashing succeeds
- deNIST/dedupe/family succeed
- route = train_station
- no Processing Set
- no Doc ID
- no Text/OCR
- no Detection
- no review promotion
- job completes with 0 exceptions

## Discovery Regression

### PDF
PASS

### XLSX
PASS

### Unknown Extension
PASS

Same common-core requirements as Capture.

## Core Rule

No new file format may modify the protected ingestion spine.

New formats must be implemented through:

1. Train Station routing
2. Dedicated adapter
3. Normalized adapter output
4. Re-entry into the protected shared ingestion pipeline

## Adapter Rule

Adapters may:
- inspect format-specific structure
- expand containers
- extract child documents
- produce normalized native/text/metadata artifacts
- establish provenance needed by the common pipeline

Adapters may not:
- assign final INSYT Doc IDs independently
- implement a separate dedupe engine
- implement a separate deNIST engine
- bypass Processing Sets
- bypass Train Station registration
- bypass shared Detection Ready handoff
- modify the protected ingestion stages
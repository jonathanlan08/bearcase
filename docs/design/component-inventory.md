# Component Inventory

Location: `apps/web/src/components/`. Primitives are headless (Radix) + Tailwind. Every component documents states: default, hover, focus, active, disabled, loading, error where applicable.

## Foundation (`ui/`)

| Component | Notes |
|---|---|
| `Button` | variants primary/secondary/ghost/danger; sizes sm/md; `loading` shows inline Evidence Link draw; icon+label only |
| `Input`, `NumberInput`, `Select`, `Radio`, `Checkbox`, `Slider` | label above, helper/error below, unit suffix support |
| `Field` | wraps label/control/help/error and wires `aria-describedby` |
| `Dialog`, `Sheet` | Radix Dialog; sheet variant for mobile |
| `Tabs`, `Tooltip`, `DropdownMenu`, `Popover` | Radix |
| `Table` | semantic table, sticky header, sticky first column option, `caption`, sortable headers with `aria-sort` |
| `Skeleton` | exact-layout skeletons |
| `Toast` | region with `role="status"`, undo action |
| `EmptyState`, `ErrorState` | symbol + sentence + action; error shows request id |
| `MicroLabel` | mono uppercase label |
| `Kbd` | keyboard hints |

## Domain (`domain/`)

| Component | Notes |
|---|---|
| `EvidenceLinkMark` | brand symbol; `animate` prop draws the line |
| `StatusGlyph`, `StatusChip` | four claim statuses + covenant warning/breach |
| `ConfidenceMeter` | 5 segments + numeric |
| `CitationChip` | `CIM p.3`, `IS!C7`, `row 14`; click → viewer; hover/focus → highlight |
| `ClaimRow`, `ClaimLedger` | roving tabindex list, keyboard map |
| `EvidencePanel`, `EvidenceCard` | supporting/contradicting groups |
| `ReviewControls`, `CorrectionDialog` | accept/reject/correct |
| `DocumentTable`, `UploadZone`, `ProcessingDrawer`, `JobProgress` | Deal Room |
| `DocumentViewer` | page text, sheet grid, CSV rows; locator scroll + highlight |
| `PeriodTable` | FY columns, cell citations |
| `MetricCard` | value, formula disclosure, input snapshot |
| `AddbackWaterfall` | chart + table alternative |
| `ScenarioForm`, `ScenarioResults`, `CfadsBridge`, `DscrGauge`, `SensitivityGrid` | Scenario Lab |
| `ReportView`, `ReportToc`, `OutcomeBadge`, `ValidationBanner` | Report |
| `AuditTimeline` | Audit history |
| `ModeBadge`, `FictionalNotice` | shell |

## Landing (`landing/`)

`SiteNav`, `Hero` (copy + `EvidenceCoreScene` dynamic + `EvidenceCoreStatic`), `ProofStrip`, `ClaimEvidenceFigure`, `ContradictionFigure`, `WaterfallFigure`, `ScenarioFigure`, `ReportFigure`, `MethodologyStrip`, `FinalCta`, `SiteFooter`.

## Scene (`scene/`)

`EvidenceCoreScene`, `Rig`, `Documents`, `Fragments`, `Core`, `Links`, `ClaimNodes`, `ModelGrid`, `CovenantRule`, `ReportStack`, `Particles`, `useStoryboard` (progress → per-stage targets), `useQualityTier`, `useScrollProgress`.

## Acceptance checklist (per component)

- [ ] All states implemented, including loading/empty/error where relevant
- [ ] Keyboard operable with visible focus
- [ ] Non-color status cues
- [ ] Reduced-motion variant
- [ ] 375px layout verified
- [ ] Unit test for logic-bearing components (status mapping, formatting, keyboard map)

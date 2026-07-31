# Visual report v2

## Outcome

`bbu analyze-repo --output html` continues to emit one shareable HTML file, but
the file is now a self-contained investigation workspace:

- it makes no requests while loading or being explored;
- files are searchable and sortable at repository scale;
- it opens with source files and migrations in scope, while broader repository
  roles remain one selection away;
- selecting a file reveals its ownership, defect, CI, X-Ray, and coupling
  evidence in one place;
- temporal coupling is ordered by the 95% Wilson lower bound and always shows
  the numerator and both revision counts behind the ratio;
- the risk matrix and change landscape are alternate routes into the same
  selected-file evidence, not separate sources of truth.

The public boundary stays `generate_html_report(AnalysisResult) -> str`. The
CLI does not change.

## Data shape

`AnalysisResult` remains the canonical report model. The report serializes the
complete validated result rather than maintaining a second file-level schema.
It adds one presentation projection for raw coupling pairs because computed
Pydantic properties are not otherwise present in `model_dump(mode="json")`.

Each coupling row contains:

```text
file A, file B, shared revisions, revisions A, revisions B,
min(revisions A, revisions B), raw Tornhill ratio, 95% Wilson lower bound
```

Pairs have a stable, evidence-first order: Wilson lower bound, shared
revisions, raw ratio, then paths. `FileForensics.coupled_with` is not used to
reconstruct raw pairs.

Every file and coupling endpoint also carries the shared path-role
classification from `path_roles.py`. The default `Code only` scope admits
source files and migrations. A coupling pair is visible only when both
endpoints are admitted. Tests, configuration, documentation, generated files,
and other repository metadata are retained in the document and can be opted
into. Summary counts, searches, the risk matrix, and the change landscape all
derive from the current scope.

## Modules

```text
visualization/
  html.py                 small public facade and document composition
  report_data.py          AnalysisResult -> deterministic report envelope
  assets/
    brand-logo.png        README lockbox artwork, embedded in every report
    report.html           semantic shell
    report.css            responsive investigation-workspace layout
    report.js             browser indexes, selection state, views
    vendor/
      manifest.json
      echarts-6.1.0.min.js
      tabulator-6.5.2.min.js
      tabulator-6.5.2.min.css
      upstream licenses
```

`treemap.py` and `coupling_graph.py` are deleted. Their APIs encode Plotly and
Cytoscape payloads, duplicate presentation policy, and lose raw evidence.
ECharts renders the risk matrix and change landscape from the canonical
envelope. Tabulator provides the virtualized grids.

## Interaction contract

The desktop layout uses the chosen “investigation workspace” direction:
searchable evidence on the left, one selected-file panel on the right, and
spatial views below. On narrower screens the panel follows the grid. Every
chart selection calls the same `selectFile(path)` transition as the grid.
The report chrome reuses the README lockbox artwork and neon palette, while
evidence panels retain restrained semantic colours for legibility.
Evidence tables open with the strongest signal first; numeric evidence columns
also sort descending on their first click. Proportional heat bars expose the
relative magnitude of each numeric value without replacing its exact number.
The change landscape removes constant path prefixes, groups files by their
first meaningful code area, and keeps full paths and supporting values in its
tooltips.

Charts are supplementary. Decision-relevant values remain available in
keyboard-operable grids and the semantic evidence panel. Repository strings
are inserted with `textContent`; Tabulator formatters return DOM nodes; and
tooltip text is escaped.

## Offline and packaging contract

Pinned ECharts and Tabulator releases, their licenses, the README brand
artwork, and a checksum manifest ship inside the Python wheel and are inlined
into the generated document. The document contains a restrictive
content-security policy and no external scripts, styles, fonts, images, or
frames. The report application does not invoke network APIs. Bundled library
code cannot connect because the policy sets `connect-src 'none'`.

Verification covers:

1. confidence-first coupling order and complete raw evidence;
2. safe, deterministic serialization of hostile repository strings;
3. absence of external resource references and a CSP that denies connections;
4. report assets in the built wheel;
5. search, numeric sort, keyboard selection, and selected evidence on the
   generated report surface.

## Accepted tradeoffs

The HTML grows by roughly 1.6 MB to become reliably offline and usable for
large grids. The repository assumes ownership of two pinned browser libraries
and their updates. This is preferable to a bespoke virtual grid and charting
implementation, and it removes runtime CDN availability and trust from every
generated report.

The report does not invent a composite risk score. It shows the existing
change-frequency × complexity hotspot model and keeps ownership, defects, CI,
and coupling as distinct evidence.

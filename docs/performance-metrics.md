# Skill Runtime Performance Metrics

`ovos-workshop` contributes two process-local histograms to a compatible
`ovos-core` metrics endpoint through the `ovos.performance.metrics` entry-point
group:

| Metric | Boundary |
|---|---|
| `ovos_skill_handler_execution_seconds` | A registered skill handler with lifecycle metadata, including nested service calls and dialog work |
| `ovos_dialog_render_seconds` | Mustache dialog rendering performed by `speak_dialog` or a `get_response` retry |

Handler duration intentionally contains nested service-call and dialog-render
duration. These histograms explain a request hierarchically and must not be
summed as disjoint stages.

Internal bus callbacks registered without handler lifecycle metadata are not
counted as skill handlers. This keeps bus housekeeping from polluting the stage
that operators use to explain user-visible reply latency.

The histograms are fixed-cardinality and process-local. They do not contain
skill IDs, session IDs, utterances, or other user-controlled labels. Prometheus
should scrape each runtime process and aggregate the cumulative buckets before
calculating p50 or p95.

`ovos-workshop` does not open an HTTP port itself. Endpoint ownership remains in
`ovos-core`, so standalone skills do not unexpectedly expose a listener.

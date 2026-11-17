# Research roles

Seven independent extraction roles run with separate objectives and structured evidence outputs. They share the existing configured Bedrock Converse integration; the design does not select different models or regions automatically.

| Role | Focus |
|---|---|
| `company` | Officially stated identity, business, products, locations and history |
| `news` | Explicitly dated announcements and events present on the official site |
| `financial` | Reported values only, retaining the original value and qualifiers |
| `funding` | Funding, investment and M&A where the recipient/acquirer is explicit |
| `leadership` | Named leaders/directors, with former status kept distinct |
| `competitors` | Explicit competitor, alternative or market evidence; no invented lists |
| `signals` | Evidenced hiring, expansion, product or technology developments |

`verification` is a deterministic role that checks that cited source IDs exist and both quote and value are extractive substrings of stored evidence. It checks financial qualifiers and flags different same-field company/leadership/financial values at the same entity/period/unit/currency scope. Different financial periods are not automatically treated as conflicts. News, funding, competitor and signal lists are additive. These lexical rules cannot prove truth, entailment or current employment. It never changes a fact to `verified` based on model confidence. `synthesis` creates report sections and summary strings from reported/conflicting persisted facts, labels conflicts, excludes unsupported findings and summarizes only reported values; empty categories say they are not available from retrieved sources.

Each run persists status, progress, timestamps, retry count, error, structured output and available Bedrock token usage. A retry reuses completed role results and retries only eligible failed work, then re-runs verification and synthesis. Agent errors are sanitized and exposed as job/agent state.

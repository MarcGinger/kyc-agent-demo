# KYC evaluation demo

This is a local evaluation of the existing Anthropic KYC plugin, not a production KYC process. DEMO-1.0 is a set of test assumptions, not regulatory guidance. Document completeness is not identity verification and no onboarding decision is made. Review every result against the source documents. Running Claude sends the extracted document text to the configured Anthropic service; use only data you are authorised to process there.

## Setup and run

Requires Python 3, Poppler (`pdfinfo`, `pdftotext`), Git, and authenticated Claude Code (`claude auth status`). Claude Code uses the configured Anthropic account; no OpenAI model is used. Check the pack path and run from the repository root:

```sh
python3 demo/run.py --pack /absolute/path/to/person-pack --type person --date 2026-11-15 --output demo/runs/person-1 --model sonnet
python3 demo/run.py --pack /absolute/path/to/company-pack --type company --date 2026-11-15 --output demo/runs/company-1 --model sonnet
python3 -m unittest discover -s demo -p 'test_*.py'
python3 scripts/check.py
```

The output directory must not exist and cannot overlap the pack. In-repository outputs are restricted to `demo/runs/`, which is ignored; `packs/` and `demo/local/` are also ignored. Store other input and result paths outside Git. Never put credentials in the repository. Original files are read only. All regular files in a pack, including profiles and manifests, are inventory items and are supplied as evidence if supported. Symlinks are rejected. PDF extraction is text only; scanned or partially empty pages are flagged for human review, not OCR'd. Unsupported or unreadable files remain in the inventory. No external links or embedded content are followed. Text extraction and model output can be incomplete; inspect sources.

Each run writes `metadata.json`, raw `runtime.json` and `stderr.txt`; on successful structural checks it also writes `results.json` and `report.md`. The raw response and outputs can contain personal information. Metadata records commit, dirty status, input hashes, policy, runtime, requested and actual model usage where returned, timing and cost when available. Commit plus a dirty flag is not a reproducible source snapshot; commit changes before a definitive run. `COMPLETED` means the call and basic result-shape checks passed, not that the extraction or rule assessment is accurate. `NOT ASSESSED` remains until a person checks results against independent expectations. Output validation checks basic shape and references only; it cannot establish factual accuracy or rule completeness.

Copy the appropriate `expected/*.json` template to a private location, populate it independently, and compare with the results manually. Expected answers never enter the agent prompt. Label any Codex-derived expectations provisional pending human verification. The templates are intentionally unset; no accuracy score is claimed.

## Baseline and adapted variant

Starting commit: `3e32c2287dcb637c184c01cc0ad82d6af7e9bb0f`. The untouched plugin was run first against the available person pack using Claude Code 2.1.325, the plugin agent, Read/Grep/Glob and `--strict-mcp-config`; no screening server was supplied. It completed, reported screening not performed and did not receive a fixed assessment date. Its raw result and provenance are locally in ignored `demo/runs/baseline-person/`. It was not independently checked for accuracy. A company baseline could not be run because its pack was unavailable.

The adapted local runner loads the same plugin agent and skills, supplies the demo policy and page-labelled extracted text, disables Claude's tools and MCP access, and validates the returned result shape. This is a different execution configuration, not a replacement agent or a managed-agent deployment. Inventory and hashes are computed locally. The plugin's full workflow refers to workers and screening that are not wired in this local configuration. Rules, facts, and page references are model proposals requiring review; screening is forcibly recorded as `NOT PERFORMED`. Output cannot approve onboarding.

## Source inspection and limits

* The managed `doc-reader` schema has only packet ID, entity name/country and flat UBO name/percentage, fewer fields than `kyc-doc-parse` specifies. This managed schema is not used by the local runner.
* `deploy-managed-agent.sh` deletes `output_schema` and contains no invocation of `scripts/validate.py`; its claim of a validation wrapper is unsupported by the script. The local runner performs its own limited structural validation, not managed-worker validation.
* The managed orchestrator and rules-engine enable all tools on the screening MCP server. The local runner uses strict MCP configuration and no tools, so this configuration does not apply to it.
* The extraction skill and managed schema represent owners as flat lists, while the rules skill refers to chain depth; the available representation does not reliably establish ownership-chain depth. The demo does not score depth.
* `screening-mock-provider` is accessible. Its HTTP simulator creates stateful screening jobs and defaults unmapped subjects to clear. It is not a read-only connector, and that default must not be treated as actual screening. A controlled read-only fixture adapter is a later milestone, after both document workflows work; it is not implemented here.

The initial repository check reports three missing bundled skill sources for meeting-prep-agent (`client-report`, `client-review`, `investment-proposal`), unrelated to this demo. Company execution, independent expected results and accuracy assessment remain outstanding.

# Local evidence review

This UI is a local evidence-review demo, not identity verification or onboarding approval. It consumes existing completed document-only runs; it makes no model calls and sends no evidence to an external service.

From the repository root, with both packs and existing runs available:

```sh
python3 demo/review_ui/server.py \
  --person-pack packs/person-sipho-nkosi \
  --company-pack packs/company-amberfield-digital-studio-pty-ltd \
  --runs-dir demo/runs \
  --reviews-dir demo/local/evidence-reviews \
  --port 8765
```

Open `http://127.0.0.1:8765`. Set each path to the appropriate local directory if your packs or runs are elsewhere. The server uses Python 3, Git, `pdfinfo`, `pdftoppm` and `pdftotext`; it binds only to `127.0.0.1`. Stop it with Ctrl-C. It accepts only clean-tree completed runs with rule outcomes and a policy available at the recorded commit; other historical runs are omitted because their exact policy cannot be established. Results, metadata and the historical policy are hashed into the review identity. Original source files are checked against the hashes in the run inventory before display. A changed or missing source is flagged, and a changed run creates a separate review.

Choose a pack and run, then click a source citation or select a document. Use page and zoom controls to inspect it. For fact citations on PDFs with a text layer, the viewer highlights a unique complete token match for the proposed value and scrolls to it. Matching ignores case and punctuation and removes the explicit `(synthetic reference)` annotation. The highlight is a navigation aid, not verification. Scans, image files, repeated matches, paraphrases and values without a unique match show no highlight; review the original manually. Facts, missing values and rule outcomes each require a review disposition before **Finish evidence review** is enabled. Corrections and inability-to-verify reasons are saved when submitted, alongside the original item, in the configured review directory. That directory must not overlap a pack or run directory; `demo/local/` is ignored. Exports contain sensitive evidence and must be saved outside Git. The screen's Review summary tab exports JSON or text. Finishing is not an approval.

Start and pause the timer explicitly. A hidden page requests a pause and requires an explicit resume. The server permits only one active review timer across tabs and runs. Heartbeats persist active seconds every five seconds; if a tab or server disappears unexpectedly, the unacknowledged interval since the last heartbeat is discarded. This avoids crediting unseen time but may undercount a short interval. The timer is not a manual baseline and cannot establish time saved.

Current runs contain fact citations but generally do not have structured rule citations. The UI flags these as missing and does not infer them from prose; reviewers should inspect the referenced documents and decide whether support is complete. OCR labels are document-level extraction status, not confidence. Source-file hashes, run-artifact hashes, policy version and commit bind a review; they do not establish factual accuracy. A filename filter and path confinement reduce accidental exposure but are not a content classifier. Only use trusted local packs and directories.

Tests:

```sh
python3 -m unittest discover -s demo/review_ui -p 'test_*.py'
python3 -m unittest discover -s demo -p 'test_*.py'
python3 scripts/check.py
```

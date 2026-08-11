# Human Adjudication Queue

Pairs where a blind judge explicitly requested human adjudication, or where the
two independent judges disagreed on the winner. These are unresolved by design:
the coordinator does not manufacture consensus on project intent the fixtures do
not establish.

## Stage 1 — 25 golden PR fixtures

Flagged pairs: 1

| case | run | judge | judge-winner | reason (truncated) |
|---|---|---|---|---|
| `golden-duplicate-existing-thread` | 2 | secondary | new_skill | Both outputs correctly respect the preview-only instruction, correctly avoid opening a duplicate inline comment on the existing unresolved '.mdc frontend classifier' thread, and both anchor the findin |

## Stage 2 — 100 official-style evals

Flagged pairs: 126

| case | run | judge | judge-winner | reason (truncated) |
|---|---|---|---|---|
| `001-01-docs_typo-initial_preview` | 1 | secondary | new_skill | Both outputs are near-identical refusals: neither produced the expected preview-only coordinated review (no compact classification, no four-mission structure, no approve decision, no QA Spec), and bot |
| `002-01-docs_command_update-initial_preview` | 1 | secondary | tie | Both outputs reached the same substantive result: neither could locate any PR content (no repo, no diff, no platform access) and both refused to fabricate a review rather than invent findings, which i |
| `003-01-ui_copy_only-initial_preview` | 1 | secondary | tie | Neither output produced the expected preview review: both report that no PR, repository, or diff is reachable in the environment, so neither classifies effort, reaches an approve decision, separates p |
| `004-01-mechanical_rename-initial_preview` | 1 | primary | tie | Neither system had an actual PR, diff, or repository to review, and both correctly refused to fabricate a review, stayed preview-only, performed no external mutation, and asked for one of three concre |
| `004-01-mechanical_rename-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: neither produced the expected preview review (no four-mission wave, no focused classification, no approve decision, no QA Spec), because both concluded no |
| `006-01-test_name_cleanup-initial_preview` | 1 | primary | tie | Both outputs reached the same correct terminal behavior for the situation they describe: no reviewable PR exists (no git repo, no diff, no PR reference), so both abstained honestly rather than fabrica |
| `006-01-test_name_cleanup-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: they found no repository, no diff, and no PR reference in the environment, and both declined to fabricate a review rather than inventing a 'test name clea |
| `007-01-comment_accuracy-initial_preview` | 1 | secondary | tie | Both outputs declined to produce the expected artifact, reporting that no PR, diff, git repository, or platform connection was reachable, and both list essentially the same three unblocking options. N |
| `008-01-generated_snapshot_refresh-initial_preview` | 1 | secondary | tie | Neither output produced the expected review artifact: both stopped because no PR, diff, repository, or snapshot files were present in the workspace. Both are honest, preview-only, invent no findings,  |
| `010-01-feature_flag_default-initial_preview` | 1 | secondary | tie | Neither output produced the expected artifact: no coordinated review, no focused classification, no request_changes decision, no priority/confidence separation, and no QA Spec. Both instead terminated |
| `011-01-environment_variable_add-initial_preview` | 1 | secondary | tie | Both outputs converged on the same substantive conclusion: no PR, diff, repository, or platform access existed in the workspace, so neither produced the review the fixture expected (focused classifica |
| `012-01-ci_workflow_permissions-initial_preview` | 1 | secondary | tie | Neither output produced a review: both independently determined that no PR, repo, diff, or workflow YAML was reachable in the environment, and both correctly refused to fabricate a preview rather than |
| `013-01-release_script_order-initial_preview` | 1 | secondary | tie | Neither output produced the expected artifact (a preview-only full review with request_changes, four missions, priority/confidence separation, and a real-workflow QA Spec). Both independently reached  |
| `014-01-kubernetes_rollout-initial_preview` | 1 | secondary | tie | Neither output produced the expected deliverable: no full-effort classification, no request_changes decision, no P0-P3 findings, and no QA Spec, because both concluded no PR/diff/YAML existed in the e |
| `015-01-package_manager_migration-initial_preview` | 1 | secondary | tie | Both outputs took the same substantive action: they reported that no PR, diff, git repo, or platform target existed in the environment, declined to fabricate findings, and asked for the change content |
| `016-01-dependency_major_upgrade-initial_preview` | 1 | secondary | tie | Both outputs face the same reality: no PR, repo, diff, or platform access exists in the environment, so neither can execute the four-mission review the assertions describe. Both correctly refuse to fa |
| `017-01-api_additive_field-initial_preview` | 1 | primary | tie | Both outputs faced an empty workspace with no PR, diff, or platform access, and both did the correct thing: they verified the absence of input (non-git directory, no source files, no PR metadata), ref |
| `017-01-api_additive_field-initial_preview` | 1 | secondary | new_skill | Both outputs reach the same substantive conclusion: no repository, diff, or PR metadata is present, so neither fabricates findings, and neither posts or claims submission — no critical failures on eit |
| `019-01-event_payload_rename-initial_preview` | 1 | secondary | old_prompt | Both outputs took the same path: they found no reviewable PR in the environment and declined to fabricate a preview. Neither delivered the expected artifact (full-effort classification, four first-wav |
| `020-01-sdk_method_addition-initial_preview` | 1 | secondary | tie | Both outputs reached the same substantive conclusion: no PR, diff, checkout, repository, or platform tooling was reachable, so no evidence-backed review could be produced. Both refused to fabricate fi |
| `021-01-cli_flag_semantics-initial_preview` | 1 | primary | tie | Both outputs are honest, preview-safe refusals: each found no PR content, diff, repository, or platform access, declined to fabricate a review, and asked for one of three concrete inputs (checkout, di |
| `021-01-cli_flag_semantics-initial_preview` | 1 | secondary | tie | Both outputs took the same path: they found no PR content (no .rs files, no diff/patch, no repo checkout, no platform connector) and declined to fabricate a review, listing the concrete checks perform |
| `022-01-manifest_classifier_drift-initial_preview` | 1 | secondary | tie | Both outputs took the same path: they searched for the target change, found no diff, no git repository, and no PR platform access, and stopped rather than fabricating a review. Neither delivered any o |
| `023-01-generated_client_version_skew-initial_preview` | 1 | secondary | tie | Both outputs reach the same substantive conclusion: no PR, diff, checkout, or platform access exists in the environment, so no review can be produced. Neither fabricates findings, neither posts or cla |
| `025-01-nullable_column_add-initial_preview` | 1 | secondary | new_skill | Both outputs are near-identical in substance: neither could produce the expected full review because no PR/diff existed in the environment, both remained preview-only, both documented the same concret |
| `026-01-not_null_before_backfill-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected preview review: both correctly determined no PR/diff was reachable in the environment and refused to fabricate findings, so the case's substantive assertions (full |
| `028-01-dual_read_write_window-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected artifact: no full-effort classification, no request_changes decision, no P0-P3 findings, and no QA Spec, because both concluded the diff was unavailable. Both corr |
| `029-01-backfill_idempotency-initial_preview` | 1 | primary | new_skill | Neither system had access to any PR content, and both correctly refused to fabricate a review rather than inventing findings — the honest, policy-compliant behavior. Neither committed a critical failu |
| `029-01-backfill_idempotency-initial_preview` | 1 | secondary | new_skill | Neither output produced a review: both correctly determined no PR content, diff, branch, or platform access existed and refused to fabricate findings, so neither satisfies the fixture's core expectati |
| `030-01-data_retention_policy-initial_preview` | 1 | secondary | old_prompt | Both outputs took the same path: neither produced the expected full review with request_changes, four-mission structure, priority/confidence separation, or a real-workflow QA Spec, so both score near  |
| `031-01-schema_default_change-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected artifact: both independently determined no PR, diff, repository, or SQL source existed in the environment and refused to fabricate a review. That refusal is honest |
| `032-01-rollback_only_migration-initial_preview` | 1 | primary | new_skill | The fixture contains no actual PR diff, and both outputs correctly refuse to fabricate a review, verify the workspace is empty, stay preview-only with no external mutation, and request concrete unbloc |
| `032-01-rollback_only_migration-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: neither could locate a diff, migration file, git history, or PR reference, and both correctly refused to fabricate findings rather than emit an invented p |
| `034-01-authentication_session_fix-initial_preview` | 1 | secondary | tie | Both outputs reach the same terminal state: they report that no PR, diff, repository, or Go source exists in the workspace and decline to review. Neither delivers the expected artifacts (full-effort c |
| `041-01-webhook_idempotency-initial_preview` | 1 | secondary | new_skill | Neither output produced the review the fixture expects (focused classification, four first-wave missions, request_changes, priority/confidence separation, real-workflow QA Spec); both concluded no PR  |
| `042-01-queue_retry_poison_message-initial_preview` | 1 | primary | tie | Both outputs correctly recognized that no PR, diff, repository, or platform access exists, refused to fabricate findings, stayed preview-only with no external mutation, and gave the author a clear, bo |
| `043-01-cache_key_scope-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: no PR, diff, repository, or platform access existed in the environment, so neither could produce the expected preview-only review with missions, effort cl |
| `045-01-transaction_partial_failure-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected preview-only review: both concluded the PR was unreachable and stopped to ask, so neither satisfies the fixture assertions about focused classification, request_ch |
| `047-01-job_resume_checkpoint-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: neither located any PR, diff, or Go source in the environment, so neither produced the expected focused, preview-only review with request_changes and a QA |
| `048-01-observability_new_failure-initial_preview` | 1 | primary | tie | Both outputs correctly determined that no PR, diff, repository, or platform connector exists in the environment and refused to fabricate a review, which is the only honest outcome — fabricating a prev |
| `048-01-observability_new_failure-initial_preview` | 1 | secondary | tie | Both outputs took the same path: they found no PR, diff, branch, or platform connector in the workspace and stopped rather than fabricating a review. Neither posted anything or claimed submission, nei |
| `050-01-bundle_size_regression-initial_preview` | 1 | secondary | old_prompt | Both outputs reached the same substantive conclusion: no PR, diff, or platform access existed in the environment, so neither produced the expected preview-only coordinated review (no focused classific |
| `051-01-memory_retention_listener-initial_preview` | 1 | primary | tie | Neither output could perform the fixture's coordinated review because no PR, diff, or repository was available; both correctly refused to fabricate findings, verified the absence of a target with conc |
| `051-01-memory_retention_listener-initial_preview` | 1 | secondary | tie | Both outputs are functionally identical: each concluded no PR/diff/repo was available, refused to fabricate findings, posted nothing (satisfying preview-only), and asked for the same three unblocking  |
| `052-01-algorithmic_complexity-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected preview review: both correctly determined no PR, diff, or repository was reachable and stopped rather than fabricating findings, so none of the substantive review  |
| `053-01-parallelism_ordering_tradeoff-initial_preview` | 1 | secondary | tie | Both outputs are substantively identical: each searched for the review target, found no repository, diff, or PR platform access, and stopped to request the diff/branch/PR reference rather than fabrica |
| `055-01-focus_loss_modal-initial_preview` | 1 | secondary | tie | Both outputs are substantively the same response: each searched the workspace, found no repository, TypeScript source, diff, or PR metadata, and stopped rather than fabricating a review of a 'focus lo |
| `057-01-undo_redo_state-initial_preview` | 1 | secondary | tie | Both outputs face the same situation: no reviewable PR, diff, repository, or platform connector exists in the environment, so neither produced the expected focused four-wave preview with request_chang |
| `059-01-screen_reader_label-initial_preview` | 1 | primary | tie | Both outputs independently report the same environmental fact: no PR, diff, repository, or platform tooling exists to review, so neither could produce the expected preview. Both correctly refused to f |
| `059-01-screen_reader_label-initial_preview` | 1 | secondary | new_skill | Both outputs declined to review, reporting that no diff, repository, or PR reference was available, and both correctly refused to fabricate findings — so neither delivered the expected preview-only ac |
| `060-01-stale_selection_async-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: neither found any PR content (no repo, no diff, no TypeScript source, empty input list), and both correctly refused to fabricate a review rather than inve |
| `061-01-localization_fallback-initial_preview` | 1 | primary | tie | Both outputs reached the same correct conclusion: no PR, diff, repository, or platform access exists in the environment, so producing the expected preview would require fabricating a review. Both veri |
| `061-01-localization_fallback-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: neither produced the expected preview review (focused classification, approve decision, P0-P3 separation, real-workflow QA Spec). Both instead reported th |
| `062-01-duplicate_business_rule-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: no PR, diff, repository, or platform connector was available, so neither produced the coordinated four-mission preview, focused classification, approve de |
| `063-01-incidental_similarity-initial_preview` | 1 | secondary | tie | Both outputs took the same path: they found no PR, diff, repository, or input files in the environment and stopped rather than fabricating a review. Neither produced any of the expected artifacts (fou |
| `064-01-shallow_wrapper-initial_preview` | 1 | secondary | tie | Neither output produced the expected artifact: the fixture calls for a preview-only focused review with four first-wave missions, an approve decision, priority/confidence separation, and a real-workfl |
| `065-01-volatile_dependency_adapter-initial_preview` | 1 | secondary | tie | Neither output produced a review at all: both stopped, reporting that no PR, diff, repository checkout, or platform connector was reachable. Both therefore fail the same expected behaviors (four first |
| `067-01-many_modes_state_space-initial_preview` | 1 | secondary | tie | Both outputs reached the same conclusion by the same evidence path: no git repository, no diff/patch, no PR reference, no platform access, therefore no review can be produced without fabricating findi |
| `068-01-agent_iteration_residue-initial_preview` | 1 | secondary | new_skill | Neither output produced the expected artifact: no coordinated multi-mission preview, no focused classification, no approve decision, no priority/confidence separation, and no QA Spec. Both instead sto |
| `069-01-stale_feature_flag-initial_preview` | 1 | secondary | tie | Both outputs reached the same terminal state: no PR artifact was present in the workspace, so neither produced the expected preview review (no focused classification, no approve decision, no priority/ |

_66 further flagged pairs are in `LIVE_AB_RESULTS.jsonl`._

## Stage 3 — 30 real SWE-PRBench PRs

Flagged pairs: 0



# Design: Stop the Incremental Sync From Deleting Mail

## Context

Two mechanisms could reconcile server-side deletions into the local DB:

1. The **incremental sync** (`SyncEngine.sync()`, 5-minute timer) — fetches a windowed slice (`SEARCH SINCE <date>`) and previously purged any local row absent from that slice, bounded by a date cutoff.
2. **Deep reconciliation** (`SyncEngine.deep_reconcile()`, timer) — walks every folder, diffs the *full* server UID set against local rows, and purges only what the complete enumeration proves is gone, guarded by an empty-folder safety rail.

Only (2) operates on complete information. (1) was structurally unable to distinguish "deleted on the server" from "outside my fetch window," and the date-cutoff heuristic that tried to paper over that gap deleted live mail (see proposal). This design records why we deleted the mechanism rather than re-tuning it.

## Decision 1: Remove the incremental purge instead of fixing the cutoff

A minimal fix exists — anchor the purge cutoff to the fetch's real floor (UTC-midnight of `last_sync`'s date) so the purge window can never reach earlier than the fetch looked. It closes the observed one-day band.

We rejected it as the end state. Even correctly anchored, the incremental purge is a deletion decision made from a partial view of the mailbox: the cutoff still has to reconcile a Date-header-vs-INTERNALDATE, local-vs-UTC, day-granular boundary, and any residual skew is paid in deleted user mail. The failure mode is irreversible (lost mail) and the upside is marginal (deletions reconcile in 5 minutes instead of a day). For an email client, that trade is wrong. We keep the anchored-cutoff reasoning in the git history as the stopgap, but the shipped state is: the incremental sync does not delete.

## Decision 2: Deep reconciliation owns deletion reconciliation, and runs daily

With the incremental purge gone, deep reconciliation is the only thing that mirrors server-side deletions. Weekly is too coarse for that responsibility — a message deleted elsewhere would haunt the local inbox for up to a week. Daily at 03:00 bounds the staleness to ~24h while keeping the cost trivial: deep reconciliation is a structural UID diff with no body refetch and no AI classification (~seconds per run on this deployment). The empty-folder safety rail already protects deep's purges against enumeration failure, so making it the sole deleter does not reintroduce the mass-purge risk.

## Decision 3: User-initiated deletions are not affected

The thing being removed is *inference of deletions made elsewhere*. Deletions a user performs inside cairn-mail flow through the pending-operations queue and `db.delete_message`, applied to the local row immediately and pushed to the provider. That path is untouched, so the UI stays instant.

## Decision 4: Keep the truncation warning, drop the truncation tracking

The IMAP provider logged a warning and recorded truncated folders so the purge could skip them (purging against a truncated fetch was the same data-loss shape). With no purge, the *tracking* is dead code and is removed along with `get_last_queried_imap_folders()` / `get_truncated_folders()`. The human-facing warning stays — truncation is still worth surfacing — reworded to note that older messages are simply deferred to a later sync, not at risk.

## Non-goals

- Gmail server-side-deletion reconciliation. Gmail is skipped by deep reconciliation (stable-ID/label model breaks the per-folder "absence == deletion" diff — see the deep-sync change's design). Removing the incremental purge does not change Gmail's behavior, because the purge never ran for Gmail (it gated on `imap_folder` and IMAP-only provider methods). Gmail therefore has no automatic external-deletion reconciliation today; closing that needs a separate label-aware design.
- Faster-than-daily deletion reconciliation. If the daily lag proves annoying, the deep cadence is a single NixOS option (`services.cairn-mail.sync.deep.onCalendar`).

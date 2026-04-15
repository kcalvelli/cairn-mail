# Implementation Tasks

## 1. Configuration Simplification

### 1.1 Tag Taxonomy Changes

- [x] 1.1.1 Create expanded default tag taxonomy constant
  - Define 35 tags with categories: Priority, Work, Personal, Finance, Shopping, Travel, Developer, Marketing, Social, System
  - Include descriptions for AI classification
  - Add category metadata for color derivation

- [x] 1.1.2 Update NixOS module options
  - Add `ai.useDefaultTags` option (default: true)
  - Change `ai.tags` semantics to additive (append to defaults)
  - Add `ai.excludeTags` option (list of tag names to remove)
  - Add `ai.labelColors` for global color overrides
  - Add `ai.labelPrefix` (default: "AI")

- [x] 1.1.3 Implement tag merging logic
  - Create function to merge defaults + custom - excluded
  - Handle custom tag overriding default description
  - Validate no duplicate tag names

- [x] 1.1.4 Implement color derivation
  - Create category-to-color mapping
  - Implement hash-based color for unknown categories
  - Allow explicit overrides via `ai.labelColors`

### 1.2 Sync Configuration Changes

- [x] 1.2.1 Add top-level sync options
  - Add `sync.frequency` at module level (default: "5m")
  - Add `sync.maxMessagesPerSync` (default: 100)
  - Add `sync.enableWebhooks` (default: false)

- [x] 1.2.2 Support per-account sync overrides
  - Keep `accounts.*.sync` for overrides
  - Implement inheritance from top-level sync

- [N/A] 1.2.3 Add deprecation warnings - deferred (no users on old config)

### 1.3 Config Loader Updates

- [x] 1.3.1 Update config loader for new structure
  - Handle `useDefaultTags` merging
  - Process `excludeTags` filtering
  - Apply color derivation

- [N/A] 1.3.2 Add backward compatibility layer - deferred (no users on old config)

- [x] 1.3.3 Update runtime config generation
  - Generate merged tag list for AI classifier
  - Include color mappings in account settings

## 2. Drafts Management

### 2.1 Backend Changes

- [x] 2.1.1 Add draft count endpoint
  - Create `GET /api/drafts/count` endpoint
  - Return `{ count: number }`
  - Cache count for performance

- [x] 2.1.2 Add partial draft support
  - Allow saving drafts without recipient
  - Allow saving drafts without subject
  - Validate only on send, not on save

### 2.2 Compose Page Improvements

- [x] 2.2.1 Add Save Draft button
  - Add "Save Draft" button next to "Send"
  - Show loading state during save
  - Show success confirmation

- [x] 2.2.2 Implement auto-save
  - Detect content changes
  - Debounce saves (30 second interval)
  - Show save status indicator ("Saving...", "Saved at X:XX")
  - Skip auto-save for empty compose

- [x] 2.2.3 Add unsaved changes protection
  - Track dirty state (changes since last save)
  - Show confirmation dialog on close/navigate
  - Offer "Save Draft", "Discard", "Cancel" options
  - Use browser beforeunload for page close

- [x] 2.2.4 Improve draft loading
  - Load all draft fields including attachments
  - Set draft ID for subsequent saves
  - Show "Editing draft" indicator

### 2.3 Sidebar Updates

- [x] 2.3.1 Add draft count badge
  - Fetch draft count on mount
  - Update count after save/delete
  - Show badge only when count > 0

- [N/A] 2.3.2 Add drafts count hook - deferred (inline approach works)

### 2.4 Drafts Page Improvements

- [x] 2.4.1 Improve draft list sorting
  - Sort by updated_at descending (most recent first)
  - Show relative time ("5 minutes ago")

- [x] 2.4.2 Add quick actions
  - Add "Edit" button (already navigates)
  - Show delete confirmation
  - Add empty state with "Compose" CTA

## 3. Settings Maintenance Panel

### 3.1 Backend Maintenance Endpoints

- [x] 3.1.1 Create maintenance router
  - Add `src/cairn_mail/api/routes/maintenance.py`
  - Register router in main app

- [x] 3.1.2 Add reclassify all endpoint
  - Create `POST /api/maintenance/reclassify-all`
  - Accept optional `overrideUserEdits` boolean
  - Return job ID for progress tracking

- [x] 3.1.3 Add reclassify unclassified endpoint
  - Create `POST /api/maintenance/reclassify-unclassified`
  - Skip messages with existing classification
  - Return job ID for progress tracking

- [x] 3.1.4 Add progress tracking
  - Create `GET /api/maintenance/jobs/{job_id}` endpoint
  - Return `{ status, progress, total, errors }`
  - Store job state in memory (not persistent)

- [x] 3.1.5 Add statistics refresh endpoint
  - Create `POST /api/maintenance/refresh-stats`
  - Recalculate tag counts
  - Return new statistics

- [x] 3.1.6 Add cancel operation endpoint
  - Create `POST /api/maintenance/jobs/{job_id}/cancel`
  - Set cancellation flag
  - Gracefully stop at next batch

### 3.2 Reclassification Logic

- [x] 3.2.1 Implement batch reclassification
  - Process in batches of 50 messages
  - Update progress after each batch
  - Check cancellation flag between batches

- [x] 3.2.2 Handle user-edited tags
  - Track which classifications were user-edited
  - Option to skip or override user edits
  - Preserve feedback records

- [x] 3.2.3 Add error handling
  - Continue on individual message errors
  - Log errors with message IDs
  - Report error count in final result

### 3.3 Frontend Maintenance Panel

- [x] 3.3.1 Add Maintenance tab to Settings
  - Add tab with wrench icon
  - Create MaintenancePanel component

- [x] 3.3.2 Create operation cards
  - "Reclassify All Messages" with description
  - "Reclassify Unclassified Only" with description
  - "Refresh Statistics" with description
  - Each with action button

- [x] 3.3.3 Add confirmation dialogs
  - Confirm before reclassify operations
  - Show message count and estimated time
  - Option for "override user edits" checkbox

- [x] 3.3.4 Add progress display
  - Show progress bar during operations
  - Display messages processed / total
  - Add cancel button
  - Show completion summary

- [x] 3.3.5 Add operation history
  - Show last operation timestamp and result
  - Display "No recent operations" if none

### 3.4 Tag Taxonomy Panel Updates

- [x] 3.4.1 Fetch active tag configuration
  - Add endpoint to return merged tag list
  - Include "default" vs "custom" flag per tag

- [x] 3.4.2 Update display with badges
  - Show "Default" badge for built-in tags
  - Show "Custom" badge for user-defined tags
  - Group by category with colors

- [x] 3.4.3 Show config status
  - Display whether `useDefaultTags` is enabled
  - Show excluded tags count if any

## 4. Testing

- [N/A] 4.1 Configuration tests - deferred (working in production)
- [N/A] 4.2 Draft management tests - deferred (working in production)
- [N/A] 4.3 Maintenance operation tests - deferred (working in production)

- [x] 4.4 Manual testing checklist
  - [x] New tag config works with useDefaultTags=true
  - [x] Custom tags append to defaults
  - [x] Save Draft button works
  - [x] Auto-save triggers after changes
  - [x] Close confirmation shows for unsaved changes
  - [x] Draft count badge updates
  - [x] Reclassify All shows progress
  - [x] Statistics refresh updates counts

## 5. Documentation

- [x] 5.1 README already covers features
- [N/A] 5.2 NixOS module docs - options are self-documenting
- [x] 5.3 Settings panels have inline descriptions

## Dependency Order

```
1. Configuration (1.x)
   └── NixOS module must change first
   └── Config loader updates follow

2. Tag taxonomy (1.1.x)
   └── Required for maintenance reclassify

3. Drafts backend (2.1.x)
   └── Before frontend changes

4. Drafts frontend (2.2.x - 2.4.x)
   └── After backend endpoints exist

5. Maintenance backend (3.1.x - 3.2.x)
   └── After tag taxonomy is finalized

6. Maintenance frontend (3.3.x - 3.4.x)
   └── After backend endpoints exist

7. Testing (4.x)
   └── After implementation complete

8. Documentation (5.x)
   └── After all features stable
```

## Parallelizable Work

- Configuration (1.x) and Drafts backend (2.1.x) can proceed in parallel
- Drafts frontend (2.2.x) can start after backend, parallel to maintenance
- Testing can be written incrementally as features complete

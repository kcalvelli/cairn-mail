# Change: Improve Configuration, Tags, Drafts & Maintenance UX

## Why

The current user experience has several pain points:

1. **Confusing Nix Configuration**: Tag/label settings are split across `ai.tags` (definitions) and `accounts.*.labels` (colors/prefix), requiring users to maintain duplicate lists. This is repetitive boilerplate that's error-prone.

2. **Limited Drafts Workflow**: Users can only see drafts created by other email clients. There's no explicit "Save Draft" action in the compose UI, and the workflow for resuming draft composition is unclear.

3. **Limited Tag Taxonomy**: The default 9 tags are insufficient for most users. The settings page displays 35+ tags but these aren't actually used - they're just display placeholders. Users should get a rich default taxonomy with an option to customize.

4. **No Maintenance Tools**: Users have no way to trigger maintenance operations like reclassifying all messages when they update their tag taxonomy or AI model.

## What Changes

### Configuration Simplification
- **BREAKING**: Remove `sync` and `labels` from account-level config
- Add top-level `sync` config (applies to all accounts, can be overridden per-account)
- Unify tag configuration: `ai.useDefaultTags` (bool) + `ai.tags` (custom additions only)
- Derive label colors automatically from tag names (with optional override)

### Drafts Management
- Add explicit "Save Draft" button to compose UI
- Show confirmation when closing compose with unsaved changes
- Improve drafts page with better sorting and quick actions
- Add draft count to sidebar

### Tag Taxonomy
- Expand default tags from 9 to ~35 covering: Priority, Work, Personal, Finance, Travel, Marketing, Social
- Add `ai.useDefaultTags` option (default: true) - uses expanded taxonomy
- Add `ai.tags` for user-defined tags that extend (not replace) defaults
- Add `ai.excludeTags` to remove specific defaults if unwanted

### Settings Maintenance Panel
- Add "Maintenance" tab to Settings page
- Add "Reclassify All Messages" action with confirmation
- Add "Reclassify Unclassified Only" action
- Add "Refresh Tag Statistics" action
- Show last maintenance operation timestamp
- All operations are non-destructive (no data loss)

## Impact

- **Affected specs**: `configuration` (new), `drafts-management` (new), `settings-ui` (new)
- **Affected code**:
  - `modules/home-manager/default.nix` - Restructure config schema
  - `src/cairn_mail/config/loader.py` - Handle new config format
  - `src/cairn_mail/ai_classifier.py` - Use expanded tag taxonomy
  - `src/cairn_mail/api/routes/maintenance.py` - New maintenance endpoints
  - `web/src/pages/Compose.tsx` - Add save draft UX
  - `web/src/pages/SettingsPage.tsx` - Add maintenance panel
  - `web/src/components/Sidebar.tsx` - Add draft count badge

## Migration

For existing users with custom `ai.tags` config:
- Their tags will continue to work
- Setting `useDefaultTags = false` preserves exact current behavior
- Setting `useDefaultTags = true` (new default) adds the expanded taxonomy plus their custom tags

# Design: Configuration, Tags, Drafts & Maintenance Improvements

## Context

cairn-mail uses a NixOS/home-manager module for declarative configuration. The current config structure evolved organically, leading to:
- Duplicated settings across accounts
- Unclear relationship between AI tags and provider labels
- Missing UX features for draft management
- No maintenance operations accessible to users

## Goals / Non-Goals

**Goals:**
- Simplify Nix configuration with sensible defaults
- Provide a rich default tag taxonomy (opt-out rather than opt-in)
- Enable explicit draft save/resume workflow
- Expose safe maintenance operations in the UI

**Non-Goals:**
- Runtime config editing (Nix remains source of truth)
- Per-account tag taxonomies (global only)
- Destructive maintenance operations (no permanent deletion)
- Auto-migration of existing classifications

## Decisions

### Decision 1: Tag Taxonomy Structure

**Chosen:** Expand defaults with user additions

```nix
ai = {
  useDefaultTags = true;  # Use expanded 35-tag taxonomy
  tags = [                # Additional user tags (appended to defaults)
    { name = "client-acme"; description = "Emails from ACME Corp"; }
  ];
  excludeTags = [ "hobby" ];  # Remove unwanted defaults
};
```

**Why:**
- Most users want comprehensive tagging out of the box
- Custom tags are additive, not replacing
- Exclusion list handles edge cases without complexity

**Alternative considered:** Replace-all mode
- Rejected: Breaking change, requires users to copy 35 tags to customize one

### Decision 2: Label Color Derivation

**Chosen:** Auto-derive colors from tag names, allow override

```nix
# Instead of per-account:
accounts.personal.labels.colors.work = "blue";

# Use global with smart defaults:
ai.labelColors = {
  # Only specify overrides, defaults derived from tag categories
  work = "blue";  # Override default
};
```

**Color defaults by category:**
- Priority (urgent, important, review): red
- Work (work, project, meeting, deadline): blue
- Personal (personal, family, friends): purple
- Finance (finance, invoice, payment, expense): green
- Travel (travel, booking, itinerary, flight): cyan
- Marketing (marketing, newsletter, promotion): orange
- Social (social, notification, update, reminder): teal
- System (junk, spam): gray

**Why:**
- Eliminates 90% of color configuration
- Consistent colors across accounts
- Still customizable when needed

### Decision 3: Sync Configuration Location

**Chosen:** Top-level with per-account override

```nix
# Global default
sync = {
  frequency = "5m";
  maxMessagesPerSync = 100;
};

# Per-account override (optional)
accounts.work.sync.frequency = "1m";  # More frequent for work
```

**Why:**
- Most users want same sync settings across accounts
- Per-account override available when needed
- Cleaner than repeating in every account block

### Decision 4: Draft Save UX

**Chosen:** Explicit save button + auto-save + close confirmation

**Compose page changes:**
1. Add "Save Draft" button next to "Send"
2. Auto-save draft every 30 seconds (if changes detected)
3. Show "Unsaved changes" indicator
4. Confirm dialog when closing with unsaved changes
5. Show draft count badge in sidebar

**Why:**
- Explicit control gives user confidence
- Auto-save prevents data loss
- Matches common email client patterns

### Decision 5: Maintenance Operations

**Chosen:** Non-destructive operations only, in Settings page

**Available operations:**
| Operation | Description | Destructive |
|-----------|-------------|-------------|
| Reclassify All | Re-run AI on all messages | No (updates tags) |
| Reclassify Unclassified | AI only on messages without tags | No |
| Refresh Statistics | Recalculate tag counts | No |
| Clear AI Cache | Reset confidence scores | No |

**Why:**
- Safe operations users can run without fear
- Useful after changing AI model or tag taxonomy
- Hidden in settings (power-user feature)

**Rejected operations:**
- Delete all messages (destructive)
- Reset database (destructive)
- Bulk delete tags (could lose user work)

### Decision 6: Default Tag Taxonomy

**Expanded taxonomy (35 tags):**

```nix
[
  # Priority
  { name = "urgent"; description = "Time-sensitive, requires immediate attention"; }
  { name = "important"; description = "High priority but not time-critical"; }
  { name = "review"; description = "Needs review or decision"; }

  # Work
  { name = "work"; description = "General work-related emails"; }
  { name = "project"; description = "Project updates and discussions"; }
  { name = "meeting"; description = "Meeting invites, agendas, notes"; }
  { name = "deadline"; description = "Tasks with deadlines"; }

  # Personal
  { name = "personal"; description = "Personal correspondence"; }
  { name = "family"; description = "Family-related emails"; }
  { name = "friends"; description = "Emails from friends"; }
  { name = "hobby"; description = "Hobbies and personal interests"; }

  # Finance
  { name = "finance"; description = "Financial matters"; }
  { name = "invoice"; description = "Invoices and bills"; }
  { name = "payment"; description = "Payment confirmations and receipts"; }
  { name = "expense"; description = "Expense reports and reimbursements"; }

  # Shopping
  { name = "shopping"; description = "Order confirmations, tracking"; }
  { name = "receipt"; description = "Purchase receipts"; }
  { name = "shipping"; description = "Shipping notifications"; }

  # Travel
  { name = "travel"; description = "General travel emails"; }
  { name = "booking"; description = "Reservations and bookings"; }
  { name = "itinerary"; description = "Trip itineraries"; }
  { name = "flight"; description = "Flight confirmations and updates"; }

  # Developer
  { name = "dev"; description = "Developer notifications"; }
  { name = "github"; description = "GitHub notifications"; }
  { name = "ci"; description = "CI/CD build notifications"; }
  { name = "alert"; description = "System alerts and monitoring"; }

  # Marketing
  { name = "marketing"; description = "Marketing emails"; }
  { name = "newsletter"; description = "Newsletter subscriptions"; }
  { name = "promotion"; description = "Promotional offers"; }
  { name = "announcement"; description = "Company/product announcements"; }

  # Social
  { name = "social"; description = "Social media notifications"; }
  { name = "notification"; description = "App and service notifications"; }
  { name = "update"; description = "Account and service updates"; }
  { name = "reminder"; description = "Reminders and follow-ups"; }

  # System
  { name = "junk"; description = "Spam and unwanted mail"; }
]
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Breaking existing configs | Clear migration docs, `useDefaultTags = false` preserves old behavior |
| Too many default tags | AI handles it well; users can exclude unwanted tags |
| Reclassify is slow | Show progress indicator, allow cancellation |
| Auto-save conflicts | Debounce saves, show save status |

## Migration Plan

1. **Phase 1**: Add new config options alongside old ones (backward compatible)
2. **Phase 2**: Deprecation warnings for old config structure
3. **Phase 3**: Remove old config structure in next major version

For immediate use:
- `useDefaultTags = true` is new default
- Existing `ai.tags` configs continue working
- Users can migrate incrementally

## Open Questions

1. **Reclassification batch size**: How many messages per batch to avoid timeout?
   - Tentative: 50 messages, with progress callback

2. **Draft auto-save interval**: 30 seconds reasonable?
   - Tentative: Yes, matches Google Docs behavior

3. **Tag color assignment algorithm**: How to assign colors to custom tags?
   - Tentative: Hash tag name to pick from color palette

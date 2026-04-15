# Change: Improve Message Reading Experience

## Why

The current message reading experience is functional but basic. Users need a richer, more productive reading experience that matches modern email clients like Gmail, Outlook, and Apple Mail.

**Current limitations:**
1. **No thread view** - Each message is viewed in isolation; users can't see conversation context
2. **Basic HTML rendering** - No inline images, no remote image blocking, poor dark mode support
3. **No quote collapsing** - Long email chains show all quoted text expanded, cluttering the view
4. **Limited mobile experience** - Reading pane doesn't adapt well to small screens
5. **No keyboard navigation** - Can't quickly move between messages without mouse/touch
6. **No print support** - No way to print or export messages
7. **No sender context** - No avatars or contact info for senders
8. **No split view** - Desktop users must navigate back/forth instead of seeing list + detail

## What Changes

### 1. Thread/Conversation View
- Group messages by thread_id into expandable conversations
- Show thread summary in message list (participant count, message count)
- Expand/collapse individual messages within a thread
- Visual timeline showing conversation flow

### 2. Enhanced HTML Rendering
- **Inline images**: Display embedded images (CID attachments)
- **Remote image blocking**: Block by default with "Load images" button
- **Dark mode adaptation**: Invert/adjust email colors for AMOLED dark theme
- **Better sanitization**: Allow more HTML while maintaining security

### 3. Quote Collapsing
- Detect quoted text patterns (`>`, `On ... wrote:`, `-----Original Message-----`)
- Collapse by default with "Show quoted text" toggle
- Smart detection for nested quote levels

### 4. Mobile Layout Improvements
- Full-width reading on mobile (no padding waste)
- Sticky header with actions while scrolling
- Swipe gestures on message detail (next/prev message)
- Bottom sheet for actions instead of top bar

### 5. Keyboard Navigation
- `j`/`k` or arrow keys for next/previous message
- `r` for reply, `f` for forward
- `e` to archive, `#` to delete
- `u` to mark unread, `o` to open/close thread
- `Escape` to go back to list

### 6. Print/Export
- Print-friendly CSS stylesheet
- "Print" button that opens browser print dialog
- Export as PDF (via print) or plain text

### 7. Sender Info
- Gravatar/avatar based on email hash
- Show sender name prominently, email as secondary
- Contact card on click (if contact info available)

### 8. Reading Pane (Desktop)
- Split view: message list on left, detail on right
- Resizable pane divider
- Toggle between split and full-page views
- Remember preference in localStorage

## Impact

- **Affected files:**
  - `web/src/pages/MessageDetailPage.tsx` - Major refactor
  - `web/src/pages/InboxPage.tsx` - Add reading pane layout
  - `web/src/components/MessageCard.tsx` - Thread indicators
  - `web/src/components/ThreadView.tsx` - NEW
  - `web/src/components/ReadingPane.tsx` - NEW
  - `web/src/components/QuotedText.tsx` - NEW
  - `web/src/components/SenderAvatar.tsx` - NEW
  - `web/src/hooks/useKeyboardNavigation.ts` - NEW
  - `web/src/hooks/useThread.ts` - NEW
  - `src/cairn_mail/api/routes/messages.py` - Thread grouping endpoint

- **New dependencies:**
  - None required (Gravatar is URL-based)

- **Database changes:**
  - None (thread_id already exists)

## Benefits

1. **Productivity** - Faster navigation, less clicking
2. **Context** - Thread view provides conversation history
3. **Readability** - Quote collapsing reduces clutter
4. **Accessibility** - Keyboard navigation for power users
5. **Mobile-first** - Better experience on phones
6. **Professional** - Matches expectations from modern email clients

## Trade-offs

1. **Complexity** - More code to maintain
2. **Performance** - Thread loading may be slower for large threads
3. **Bundle size** - Additional components increase JS bundle

## Implementation Order

1. **Reading Pane** (desktop foundation)
2. **Keyboard Navigation** (low effort, high impact)
3. **Thread View** (high value feature)
4. **Quote Collapsing** (improves thread readability)
5. **Enhanced HTML Rendering** (inline images, dark mode)
6. **Sender Info** (polish)
7. **Mobile Reading Improvements** (mobile-specific)
8. **Print/Export** (nice to have)

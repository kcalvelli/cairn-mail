# UI Layer Capability

## ADDED Requirements

### Requirement: Web-Based User Interface

The system SHALL provide a modern web-based user interface accessible via localhost for managing emails and AI tags.

#### Scenario: Access web UI

- **WHEN** the cairn-mail backend server is running
- **THEN** users SHALL be able to access the web UI at `http://localhost:8080` (configurable port)
- **AND** the UI SHALL load within 2 seconds on a modern browser
- **AND** the UI SHALL work on Chrome, Firefox, Safari, and Edge (latest versions)

#### Scenario: Responsive design

- **WHEN** the web UI is accessed from different screen sizes
- **THEN** the UI SHALL adapt to mobile (< 768px), tablet (768px-1024px), and desktop (> 1024px) viewports
- **AND** SHALL maintain usability on all screen sizes
- **AND** SHALL use touch-friendly controls on mobile devices

#### Scenario: Dark mode support

- **WHEN** a user toggles dark mode in settings
- **THEN** the UI SHALL switch to a dark color scheme
- **AND** SHALL persist the preference in local storage
- **AND** SHALL respect the system dark mode preference by default

### Requirement: Message List Display

The system SHALL display email messages in a list view with AI-assigned tags, priority, and metadata.

#### Scenario: Display message list

- **WHEN** a user opens the web UI
- **THEN** the system SHALL display a list of messages from all configured accounts
- **AND** each message SHALL show:
  - Sender name and email address
  - Subject line
  - Date/time (relative format like "2 hours ago")
  - Snippet (first ~100 characters)
  - AI tags as colored badges
  - Priority indicator (icon for high priority)
  - Unread status (bold if unread)

#### Scenario: Infinite scroll

- **WHEN** a user scrolls to the bottom of the message list
- **THEN** the system SHALL automatically load the next batch of messages (50 at a time)
- **AND** SHALL display a loading indicator while fetching
- **AND** SHALL append new messages to the existing list

#### Scenario: Message sorting

- **WHEN** a user selects a sort option (date, sender, subject)
- **THEN** the message list SHALL re-sort according to the selected criteria
- **AND** SHALL default to sorting by date (newest first)

### Requirement: Tag-Based Filtering

The system SHALL allow users to filter messages by AI-assigned tags with multi-tag support.

#### Scenario: Filter by single tag

- **WHEN** a user clicks on a tag badge or selects a tag from the sidebar filter
- **THEN** the message list SHALL display only messages with that tag
- **AND** the selected tag SHALL be highlighted in the sidebar
- **AND** the URL SHALL update to reflect the filter (e.g., `?tag=work`)

#### Scenario: Filter by multiple tags

- **WHEN** a user selects multiple tags from the sidebar filter
- **THEN** the message list SHALL display messages that have ANY of the selected tags (OR logic)
- **AND** the sidebar SHALL show all selected tags as active
- **AND** a "Clear filters" button SHALL be visible

#### Scenario: Special filters

- **WHEN** a user selects a special filter from the sidebar
- **THEN** the system SHALL apply predefined queries:
  - **Inbox**: Messages with inbox label and not archived
  - **To-Do**: Messages with `todo` tag
  - **High Priority**: Messages with `prio-high` tag or `priority: "high"`
  - **Unread**: Messages marked as unread
  - **Archived**: Messages that have been auto-archived

### Requirement: Full-Text Search

The system SHALL provide full-text search across message subjects, senders, and content with instant results.

#### Scenario: Search messages

- **WHEN** a user types a query in the search bar
- **THEN** the system SHALL search across subject, sender, and snippet fields
- **AND** SHALL display matching messages within 500ms
- **AND** SHALL highlight the search term in results
- **AND** SHALL use debouncing (300ms delay) to avoid excessive API calls while typing

#### Scenario: Search with filters

- **WHEN** a user combines search with tag filters
- **THEN** the system SHALL return messages matching both the search query AND the selected tags
- **AND** SHALL display the count of matching messages

#### Scenario: Search syntax support

- **WHEN** a user enters advanced search syntax (e.g., `from:boss@company.com subject:budget`)
- **THEN** the system SHOULD parse the syntax and apply field-specific filters
- **AND** SHALL fall back to simple full-text search if syntax parsing fails

### Requirement: Tag Management

The system SHALL allow users to add, remove, and modify tags on messages with immediate sync to the provider.

#### Scenario: Add tag to message

- **WHEN** a user adds a tag to a message via the UI
- **THEN** the system SHALL update the message's tags in the database
- **AND** SHALL trigger a label update on the email provider
- **AND** SHALL show the new tag immediately in the UI (optimistic update)
- **AND** SHALL revert the change if the provider update fails

#### Scenario: Remove tag from message

- **WHEN** a user removes a tag from a message (click X on tag badge)
- **THEN** the system SHALL update the database and provider
- **AND** SHALL remove the tag from the UI immediately
- **AND** SHALL record the removal as user feedback

#### Scenario: Bulk tag operations

- **WHEN** a user selects multiple messages and applies a tag action
- **THEN** the system SHALL update all selected messages
- **AND** SHALL show a progress indicator for bulk operations
- **AND** SHALL handle partial failures gracefully (some messages succeed, others fail)

### Requirement: Real-Time Updates

The system SHALL update the UI in real-time when new messages are synced or classified without requiring manual refresh.

#### Scenario: WebSocket connection

- **WHEN** the web UI loads
- **THEN** the system SHALL establish a WebSocket connection to the backend
- **AND** SHALL display a connection status indicator (connected/disconnected)
- **AND** SHALL automatically reconnect if the connection is lost

#### Scenario: New message notification

- **WHEN** the sync engine classifies a new message
- **THEN** the backend SHALL push an event via WebSocket
- **AND** the UI SHALL add the new message to the top of the list
- **AND** SHALL display a toast notification (e.g., "New message from boss@company.com")
- **AND** SHALL update the unread count badge

#### Scenario: Classification update

- **WHEN** a message's classification is updated (reclassified or user corrects tags)
- **THEN** the backend SHALL push an update event via WebSocket
- **AND** the UI SHALL update the message's tags in the list without full refresh

### Requirement: Account Management

The system SHALL display configured accounts and allow users to view per-account statistics and trigger manual syncs.

#### Scenario: View accounts

- **WHEN** a user navigates to the Accounts page
- **THEN** the UI SHALL display all configured accounts with:
  - Email address
  - Provider type (Gmail, Outlook, IMAP)
  - Last sync timestamp
  - Sync status (syncing, idle, error)
  - Message count
  - Unread count

#### Scenario: Trigger manual sync

- **WHEN** a user clicks "Sync Now" for an account
- **THEN** the system SHALL trigger an immediate sync for that account
- **AND** SHALL display a loading spinner on the account card
- **AND** SHALL update the last sync timestamp when complete

#### Scenario: Account filtering

- **WHEN** a user selects a specific account from the account list
- **THEN** the message list SHALL display only messages from that account
- **AND** the selected account SHALL be highlighted

### Requirement: Settings and Configuration

The system SHALL provide a settings interface for customizing AI behavior, UI preferences, and sync options.

#### Scenario: View settings

- **WHEN** a user navigates to the Settings page
- **THEN** the UI SHALL display settings grouped by category:
  - **AI Settings**: Model selection, tag taxonomy, confidence threshold
  - **Sync Settings**: Frequency, webhook enable/disable
  - **UI Settings**: Theme (light/dark), default sort, messages per page
  - **Label Settings**: Label prefix, colors

#### Scenario: Update AI model

- **WHEN** a user selects a different LLM model from the dropdown
- **THEN** the system SHALL validate that the model is available in Ollama
- **AND** SHALL save the setting to the configuration
- **AND** SHALL use the new model for future classifications

#### Scenario: Customize tag taxonomy

- **WHEN** a user adds a custom tag to the taxonomy
- **THEN** the system SHALL add the tag to the allowed list
- **AND** SHALL include it in the AI classification prompt
- **AND** SHALL validate that the tag name is alphanumeric and lowercase

#### Scenario: Adjust sync frequency

- **WHEN** a user changes the sync frequency (e.g., from 5 minutes to 10 minutes)
- **THEN** the system SHALL update the backend timer configuration
- **AND** SHALL restart the sync timer with the new interval

### Requirement: Dashboard and Analytics

The system SHALL provide a dashboard with inbox statistics, tag distribution, and classification insights.

#### Scenario: View dashboard

- **WHEN** a user navigates to the Dashboard page
- **THEN** the UI SHALL display:
  - Inbox count (unread messages)
  - To-Do count (messages requiring action)
  - High priority count
  - Recent activity timeline (last 10 events: syncs, classifications)

#### Scenario: Tag distribution chart

- **WHEN** a user views the dashboard
- **THEN** the system SHALL display a chart showing tag distribution:
  - Pie chart or bar chart of message counts per tag
  - Color-coded by tag color

#### Scenario: Classification accuracy metrics

- **WHEN** user feedback data is available
- **THEN** the dashboard SHALL display:
  - Percentage of messages with user corrections
  - Most frequently corrected tags
  - Average classification confidence

### Requirement: Keyboard Shortcuts

The system SHALL provide keyboard shortcuts for common actions to improve power user productivity.

#### Scenario: Navigation shortcuts

- **WHEN** a user presses keyboard shortcuts
- **THEN** the system SHALL respond to:
  - `j` / `k`: Navigate down/up in message list (vim-style)
  - `Enter`: Open selected message
  - `/`: Focus search bar
  - `g i`: Go to Inbox
  - `g t`: Go to To-Do
  - `Esc`: Clear filters and selections

#### Scenario: Action shortcuts

- **WHEN** a user has a message selected
- **THEN** the system SHALL respond to:
  - `e`: Archive message
  - `t`: Add/remove tag (opens tag picker)
  - `x`: Select/deselect message (for bulk actions)

#### Scenario: Shortcut help

- **WHEN** a user presses `?`
- **THEN** the system SHALL display a modal with all available keyboard shortcuts

### Requirement: Error Handling and User Feedback

The system SHALL provide clear error messages and loading states for all asynchronous operations.

#### Scenario: API error display

- **WHEN** an API request fails (network error, server error, timeout)
- **THEN** the UI SHALL display a toast notification with:
  - Error message (user-friendly, not technical jargon)
  - Suggested action (e.g., "Check your connection and try again")
  - Retry button (if applicable)

#### Scenario: Loading states

- **WHEN** the UI is fetching data (messages, search results, tag updates)
- **THEN** the system SHALL display a loading indicator:
  - Skeleton screens for message list
  - Spinner for button actions
  - Progress bar for bulk operations

#### Scenario: Empty states

- **WHEN** a filter or search returns no results
- **THEN** the UI SHALL display an empty state message:
  - Friendly message (e.g., "No messages found")
  - Suggestions (e.g., "Try a different filter or search term")
  - Illustration or icon

### Requirement: Accessibility

The system SHALL comply with WCAG 2.1 Level AA accessibility standards to ensure usability for all users.

#### Scenario: Keyboard navigation

- **WHEN** a user navigates the UI using only the keyboard
- **THEN** all interactive elements SHALL be reachable via Tab key
- **AND** focus indicators SHALL be clearly visible
- **AND** focus order SHALL follow a logical sequence

#### Scenario: Screen reader support

- **WHEN** a user accesses the UI with a screen reader
- **THEN** all elements SHALL have appropriate ARIA labels and roles
- **AND** dynamic content updates SHALL announce changes via ARIA live regions
- **AND** images SHALL have alt text

#### Scenario: Color contrast

- **WHEN** displaying text and UI elements
- **THEN** the system SHALL maintain a minimum contrast ratio of 4.5:1 for normal text
- **AND** 3:1 for large text and UI components
- **AND** color SHALL NOT be the only means of conveying information

### Requirement: Performance Optimization

The system SHALL optimize the web UI for fast load times and smooth interactions.

#### Scenario: Initial load performance

- **WHEN** a user first loads the web UI
- **THEN** the system SHALL display the message list within 2 seconds
- **AND** the total bundle size SHALL be under 500KB (gzipped)
- **AND** the UI SHALL use code splitting to load routes on demand

#### Scenario: Scroll performance

- **WHEN** a user scrolls through the message list
- **THEN** the UI SHALL maintain 60 FPS scroll performance
- **AND** SHALL use virtualized rendering for lists with >100 items
- **AND** SHALL lazy-load images and avatars

#### Scenario: Network efficiency

- **WHEN** the UI makes API requests
- **THEN** the system SHALL cache responses in memory using React Query
- **AND** SHALL deduplicate identical requests
- **AND** SHALL use ETag/If-None-Match headers for conditional requests

### Requirement: Data Privacy

The system SHALL handle user email data with privacy and security best practices.

#### Scenario: No persistent storage of email content

- **WHEN** displaying messages in the UI
- **THEN** the system SHALL fetch message content from the backend on demand
- **AND** SHALL NOT cache full email bodies in browser local storage
- **AND** SHALL only cache message metadata (ID, subject, sender, snippet)

#### Scenario: Secure connection

- **WHEN** the UI communicates with the backend
- **THEN** the connection SHALL use HTTPS if the backend is configured with TLS
- **OR** SHALL warn the user if using HTTP (only acceptable for localhost)

#### Scenario: Session management

- **WHEN** the web UI is accessed
- **THEN** the system SHALL NOT require user login for localhost access
- **AND** SHALL implement authentication if exposed to network (optional feature)
- **AND** SHALL timeout inactive sessions after 1 hour (if auth is enabled)

### Requirement: Multi-Account UI Support

The system SHALL provide intuitive multi-account support in the UI with account switching and unified views.

#### Scenario: Unified inbox

- **WHEN** a user has multiple accounts configured
- **THEN** the default view SHALL display messages from all accounts in a unified list
- **AND** SHALL indicate the account for each message (icon or label)

#### Scenario: Account switcher

- **WHEN** a user clicks on the account dropdown
- **THEN** the UI SHALL display a list of all accounts
- **AND** SHALL allow selecting a single account to view
- **AND** SHALL show an "All Accounts" option to return to unified view

#### Scenario: Per-account statistics

- **WHEN** viewing account details
- **THEN** the UI SHALL display per-account inbox counts, unread counts, and last sync time
- **AND** SHALL allow triggering sync individually per account

### Requirement: Export and Backup

The system SHALL allow users to export message classifications and settings for backup or analysis.

#### Scenario: Export classifications

- **WHEN** a user clicks "Export Data" in settings
- **THEN** the system SHALL generate a JSON file containing:
  - All message classifications (message IDs, tags, timestamps)
  - User feedback (tag corrections)
  - Settings configuration
- **AND** SHALL prompt the browser to download the file

#### Scenario: Import classifications

- **WHEN** a user uploads an export file
- **THEN** the system SHALL validate the file format
- **AND** SHALL merge the imported classifications with existing data
- **AND** SHALL prompt for confirmation before overwriting existing data

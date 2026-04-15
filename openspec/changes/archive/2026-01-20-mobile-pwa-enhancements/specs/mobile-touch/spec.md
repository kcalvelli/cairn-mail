# Mobile Touch Interactions Specification

## ADDED Requirements

### Requirement: Long-Press Multi-Select
The message list SHALL support long-press gesture to enter multi-select mode without conflicting with swipe gestures.

#### Scenario: Initiating selection mode via long-press
- **GIVEN** the user is viewing the message list on mobile
- **WHEN** the user presses and holds on a message for 500ms without moving >10px
- **THEN** the app SHALL enter selection mode
- **AND** the pressed message SHALL be selected
- **AND** haptic feedback SHALL be triggered

#### Scenario: Long-press cancelled by swipe
- **GIVEN** the user begins pressing on a message
- **WHEN** the user's finger moves more than 10px before 500ms elapses
- **THEN** the long-press SHALL be cancelled
- **AND** the swipe gesture SHALL proceed normally

#### Scenario: Selecting additional messages
- **GIVEN** the app is in selection mode
- **WHEN** the user taps on any message
- **THEN** that message's selection state SHALL toggle
- **AND** the selection count SHALL update

#### Scenario: Bulk delete in selection mode
- **GIVEN** the app is in selection mode with messages selected
- **WHEN** the user taps the Delete action
- **THEN** all selected messages SHALL be moved to trash
- **AND** selection mode SHALL exit

#### Scenario: Exiting selection mode
- **GIVEN** the app is in selection mode
- **WHEN** the user taps the exit button (X)
- **THEN** selection mode SHALL exit
- **AND** all selections SHALL be cleared

---

### Requirement: Selection Mode UI
A floating toolbar SHALL appear when in selection mode to provide bulk actions.

#### Scenario: Selection toolbar appearance
- **WHEN** the app enters selection mode
- **THEN** a toolbar SHALL appear at the top of the screen
- **AND** it SHALL display the selection count
- **AND** it SHALL provide Delete, Archive, and Mark Read/Unread actions

#### Scenario: Swipe disabled in selection mode
- **GIVEN** the app is in selection mode
- **WHEN** the user attempts to swipe on a message
- **THEN** the swipe gesture SHALL be ignored
- **AND** the tap SHALL toggle selection instead

---

### Requirement: Visual Feedback During Long-Press
The user SHALL receive visual feedback during the long-press gesture.

#### Scenario: Press indicator
- **WHEN** the user begins pressing on a message
- **THEN** a subtle visual effect (scale/ripple) SHALL indicate the press
- **AND** the effect SHALL intensify as the 500ms threshold approaches

#### Scenario: Selection indicator
- **WHEN** a message is selected
- **THEN** a checkbox or highlight SHALL indicate selected state
- **AND** the visual distinction SHALL be clear in both light and dark modes

---

## PWA Features Specification

### Requirement: App Shortcuts
The PWA manifest SHALL define shortcuts for quick navigation.

#### Scenario: Home screen shortcuts
- **GIVEN** the PWA is installed on Android
- **WHEN** the user long-presses the app icon
- **THEN** shortcuts for Compose and Inbox SHALL be available

---

### Requirement: Share Target
The PWA SHALL be registered as a share target to receive content from other apps.

#### Scenario: Receiving shared text
- **GIVEN** the PWA is installed
- **WHEN** the user shares text from another app and selects Cairn Mail
- **THEN** the compose screen SHALL open
- **AND** the shared text SHALL pre-fill the message body

#### Scenario: Receiving shared URL
- **GIVEN** the PWA is installed
- **WHEN** the user shares a URL from another app
- **THEN** the compose screen SHALL open
- **AND** the URL SHALL be included in the message body

---

### Requirement: Push Notifications
The PWA SHALL support true push notifications via service worker.

#### Scenario: Push subscription
- **GIVEN** the user has granted notification permission
- **WHEN** the app loads
- **THEN** a push subscription SHALL be registered with the backend

#### Scenario: Receiving push while app closed
- **GIVEN** the user has an active push subscription
- **AND** the app is not open
- **WHEN** a new email arrives during backend sync
- **THEN** a push notification SHALL be displayed
- **AND** tapping it SHALL open the app to that message

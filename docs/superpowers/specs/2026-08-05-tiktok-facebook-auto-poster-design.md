# TikTok to Facebook Auto-Poster Design Specification

** 
**Date**: 2026-08-05

## Overview
A tool to automatically detect new videos from TikTok channels (provided by users) and upload them to corresponding Facebook Pages. Supports many-to-many mapping where one TikTok channel can post to multiple Facebook Pages, and one Facebook Page can receive videos from multiple TikTok channels.

## Core Features

### 1. Channel & Page Management
- **TikTok Channels**: Add via @username or user ID
- **Facebook Pages**: Add via Page ID, name (vanity URL), or full URL (requires access token)
- **Many-to-Many Mappings**: Create relationships where:
  - One TikTok channel → Multiple Facebook Pages
  - Multiple TikTok channels → One Facebook Page
  - View/edit/delete existing mappings

### 2. Automated Posting
- **Background Polling**: Checks for new TikTok videos every 30-60 minutes (configurable)
- **New Video Detection**: Only processes videos published after last check timestamp
- **Duplicate Prevention**: Checks database before posting to avoid re-posting same video
- **Manual Triggers**: 
  - "Check Now" button for immediate processing
  - "Backfill Historical" for processing past videos (configurable days)

### 3. Post Management
- **Title/Description**: Defaults to TikTok video's title/description
- **Edit After Posting**: Modify title/description of published Facebook posts
- **Delete Posts**: Remove from history (optionally delete from Facebook if API permits)
- **Post History**: View log with filtering (date, channel, page, status)
- **Status Indicators**: Success/failed/posting states with error details

### 4. Safety & Reliability
- **Rate Limiting**: Token bucket algorithm (10 req/min per service) to prevent API blocks
- **Retry Logic**: Exponential backoff (1s, 2s, 4s) with max 3 attempts
- **Circuit Breaker**: Pause service after 5 consecutive failures
- **Error Handling**: Detailed logging, dead letter queue for repeated failures
- **Resilience**: Database locks prevent overlapping scheduler runs
- **Monitoring**: Heartbeat mechanism, disk space checks, graceful shutdown

## Architecture

### Technology Stack
- **Backend**: FastAPI (Python), SQLModel (ORM), PostgreSQL
- **Frontend**: React (TypeScript), Tailwind CSS, shadcn/ui
- **Database**: PostgreSQL with tables for channels, pages, mappings, posted videos
- **Deployment**: Docker Compose (inherits from template)

### Components

#### Frontend
1. **ChannelManager** - Add/view/edit/delete TikTok channels
2. **PageManager** - Add/view/edit/delete Facebook Pages
3. **MappingBuilder** - Create TikTok → Facebook Page mappings (many-to-many)
4. **PostHistory** - View/post filter/search posted videos with edit/delete actions
5. **ManualControls** - "Check Now", "Backfill Historical", "Refresh Status" buttons
6. **EditPostModal** - Modify title/description of existing posts
7. **StatusDashboard** - Overview: last check time, pending videos, success/error rates

#### Backend Services
1. **TikTokService** - Poll TikTok API, extract video metadata, handle rate limits
2. **FacebookService** - Upload videos to FB Graph API, manage access tokens
3. **SchedulerService** - Background worker running on configurable interval
4. **PostingService** - Orchestrate: detect→download→upload→record (with duplicate check)
5. **API Routes** - CRUD for channels/pages/mappings, history/stats, manual triggers
6. **Database Models** - TikTokChannel, FacebookPage, ChannelPageMapping, PostedVideo
7. **Utilities** - Rate limiter, video downloader, error handler, notification system

## Data Flow

### Configuration Flow (UI → Backend)
1. User adds TikTok channel (@username) → POST `/api/tiktok-channels` → stored in `tiktok_channels`
2. User adds Facebook Page → POST `/api/facebook-pages` → stored in `facebook_pages` (encrypted token)
3. User creates mapping: TikTok channel + FB Page(s) → POST `/api/mappings` → stored in `channel_page_mappings`

### Automated Posting Flow (Scheduler → Services)
1. **Scheduler** wakes every interval (default 30-60 min)
2. For each TikTok channel:
   - `TikTokService.get_new_videos(channel_id, since_last_check)`
   - Returns new videos (id, title, description, download_url, thumbnail, posted_at)
   - Updates `tiktok_channels.last_checked`
3. For each new video:
   - For each mapped Facebook Page:
     - Check `posted_videos` for (tiktok_video_id, facebook_page_id) → skip if exists
     - Download video from TikTok URL
     - `FacebookService.upload_video(page_id, video_file, title, description)`
     - On success: Record in `posted_videos` with `status='success'`
     - On failure: Record with `status='failed'` + error message
     - Update with any user-edited title/description

### History & Status Flow (Backend → UI)
1. `GET /api/posted-videos?filters...` → PostHistory component displays:
   - Video thumbnail, title, TikTok channel, Facebook Page
   - Posted timestamp, status, edit/delete actions
2. `GET /api/stats` → StatusDashboard shows:
   - Last check time, videos pending/success/failed counts

### Manual Operations
- **Check Now**: POST `/api/tiktok/check-now` → triggers immediate scheduler run
- **Backfill**: POST `/api/tiktok/backfill?channel_id&days=7` → processes historical videos
- **Edit Post**: PUT `/api/posted-videos/{id}` → updates DB + attempts FB post update
- **Delete Post**: DELETE `/api/posted-videos/{id}` → marks as deleted (optional FB deletion)

## Database Schema

### Tables
1. **tiktok_channels**
   - id (PK), username (unique), display_name, last_checked, created_at, is_active

2. **facebook_pages**
   - id (PK), page_id (unique), name, access_token_encrypted, created_at, is_active

3. **channel_page_mappings** (many-to-many)
   - id (PK), tiktok_channel_id (FK), facebook_page_id (FK), created_at
   - Unique constraint on (tiktok_channel_id, facebook_page_id)

4. **posted_videos**
   - id (PK), tiktok_video_id (unique), facebook_post_id, tiktok_channel_id (FK), 
   - facebook_page_id (FK), title, description, posted_at, status (success/failed/deleted),
   - error_message, created_at, updated_at

5. **failed_posts** (dead letter queue for manual review)
   - Similar to posted_videos but for repeatedly failing items (>3 failures)

## Error Handling & Resilience

### API Failure Handling
- **Retry Mechanism**: 3 attempts with exponential backoff (1s, 2s, 4s)
- **Circuit Breaker**: After 5 consecutive failures → pause service for 5 minutes
- **Rate Limiting**: Token bucket (10 requests/minute per service)
- **Fallbacks**: TikTok API scraping fallback for public data
- **Token Management**: Auto-refresh Facebook long-lived tokens

### Database & System Resilience
- **Transaction Rollback**: On failure, rollback DB changes
- **Connection Pooling**: With retry logic for DB connections
- **Scheduler Lock**: Database lock (SELECT FOR UPDATE) prevents overlapping runs
- **Heartbeat**: Scheduler updates timestamp; restart if stale >10 minutes
- **Disk Monitoring**: Stop if <1GB free space
- **Daily Backups**: Automated database dumps

### User Action Safety
- **Optimistic Updates**: UI updates immediately with rollback on failure
- **Input Validation**: Sanitize/validate all inputs (username/ID formats)
- **Confirmation Dialogs**: For destructive actions (delete, unmap)
- **Undo Support**: Recover deleted posts within 24 hours

### Monitoring & Alerting
- **Critical Alerts**: Email + dashboard warning for DB/scheduler failures
- **Service Warnings**: Log warnings + UI indicators for 3+ consecutive API failures
- **Daily Summary**: Email with success/failure counts and action items
- **Admin Dashboard**: Real-time service status, last errors, retry queues

## Testing Strategy

### Unit Tests (Target: 80%+ coverage)
- Service layers: TikTokService, FacebookService, PostingService (mocked APIs)
- Utility functions: video processing, validation, date handling
- API route handlers: Request validation, response formatting
- Database models: CRUD operations

### Integration Tests
- Database operations with test PostgreSQL instance
- Full API endpoint testing with test client
- Background job integration with mocked services
- Mapping logic verification for many-to-many relationships

### End-to-End Tests (Playwright)
- User flow: Add TikTok channel → Add Facebook Page → Create mapping → Verify post in history
- Error scenarios: Simulate API failures, network issues, invalid inputs
- UI interactions: Edit post, delete post, manual triggers
- Responsive design: Mobile/tablet/desktop breakpoint testing

### Manual Testing Checklist
- [ ] Add TikTok channel by @username
- [ ] Add Facebook Page by Page ID/name/URL
- [ ] Create mapping (1 TikTok → multiple Pages)
- [ ] Verify new TikTok video triggers Facebook posts
- [ ] Check duplicate prevention (same video not posted twice)
- [ ] Test edit post functionality updates Facebook post
- [ ] Test delete post removes from history (and optionally FB)
- [ ] Verify "Check Now" button works immediately
- [ ] Test backfill functionality for historical videos
- [ ] Monitor rate limiting behavior under load
- [ ] Check error handling and retry logic

## Future Enhancements (Post-MVP)
1. **Webhook Integration**: Replace polling with TikTok/Facebook webhooks for real-time processing
2. **Advanced Scheduling**: Cron-like scheduling for specific posting times
3. **Content Transformation**: Video editing (trim, add watermark, change format) before posting
4. **Analytics Dashboard**: View engagement metrics (likes, shares, comments) from Facebook
5. **Multiple Users**: Add authentication/authorization for multi-tenant support
6. **Media Alternatives**: Support for posting images, text-only posts, live videos
7. **Notification Channels**: Slack, Email, SMS alerts for failures/successes
8. **Content Moderation**: Auto-flag potentially problematic content before posting

## Assumptions & Constraints
1. **TikTok Access**: Uses official API where possible, falls back to public scraping
2. **Facebook Access**: Requires valid long-lived user access token with pages_manage_posts permission
3. **Video Format**: Assumes TikTok provides MP4 videos compatible with Facebook upload
4. **Rate Limits**: Designed to stay within typical API limits (adjustable via config)
5. **Storage**: Temporary video storage during processing (cleaned up after upload)
6. **Single User**: Initial MVP for single user; multi-user requires auth system
7. **Timezone**: Uses UTC internally; displays in user's local timezone in UI

## Open Questions for Implementation
1. **TikTok API Access**: Should we use unofficial TikTok API libraries or official business API?
2. **Facebook Permissions**: What specific Facebook permissions are required for video posting?
3. **Video Storage**: Where should temporary video files be stored during processing?
4. **Backfill Limit**: What's reasonable maximum for historical backfill (e.g., 30 days)?
5. **Failure Threshold**: After how many consecutive failures should we alert vs auto-pause?
6. **Edit Limitations**: Does Facebook API allow editing video posts after publishing?
7. **Delete Support**: Can we delete Facebook posts via API, or just hide/unpublish?
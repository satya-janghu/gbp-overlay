# GBP Image Overlay Optimization Tool — Product Requirements Document

## 1. Overview

### 1.1 What This Tool Does

This is a web application for SEO and local-marketing teams. It automates the process of preparing images for Google Business Profile (GBP) uploads by:

1. Fetching images from client websites (via sitemap crawling)
2. Analyzing image content using AI vision
3. Matching images to the most appropriate keyword from a provided list
4. Applying text overlays (keyword + location) with intelligent placement
5. Exporting processed images as a downloadable ZIP

The theory behind this workflow: adding keyword and location text to GBP images may positively impact local SEO performance. Teams typically do this by hand in design tools like Canva. This app automates the entire pipeline.

### 1.2 Users

SEO and local-marketing practitioners. No login system. Session persistence via long-lived browser cookie (180 days). Designed for small teams (a handful of concurrent users).

### 1.3 Hosting

- **Platform:** Railway (single web container + managed PostgreSQL + Redis)
- **Storage:** Railway persistent volume mounted at `/data`
- **Domain:** Railway-provided URL or a custom domain

---

## 2. Core Workflow

The app follows a five-stage pipeline: **Setup → Crawl & Collect → Match Keywords → Preview & Confirm → Generate & Download**

### Stage 1: Project Setup

The user lands on a single-page form with the following fields:

| Field | Required | Default | Notes |
|---|---|---|---|
| Client Name | No | — | For the user's reference in download history |
| Website URL | No | — | Required only if auto-fetching images |
| Keywords | Yes | — | Textarea, one keyword per line |
| Locations | No | — | Textarea, one per line. Optional if crawling location pages (locations inferred from URLs) |
| Font | Yes | Montserrat | Dropdown picker with live preview, 9 font options |
| Images Per Page | Yes | 3 | Number input. How many images to attempt to fetch per crawled page |
| Fetch From Anywhere | No | Off | Checkbox. If on, images can be sourced from any page on the site, not just location pages |
| Image Upload | No | — | Drag-and-drop zone for manual image uploads. Optional per-image keyword/location tagging on upload |

The user must provide keywords. Everything else depends on the workflow they're using:

- **Auto-fetch workflow:** Provide URL + keywords. Locations are inferred from crawled pages.
- **Manual upload workflow:** Upload images + keywords. Assign locations manually.
- **Hybrid workflow:** Provide URL + upload some images + keywords. Mix of auto and manual.

### Stage 2: Crawl & Collect

When the user submits the form with a website URL, the app:

1. Fetches the sitemap XML from the website
2. Identifies location-specific pages by URL pattern (e.g., `/locations/city-name/`, `/service-area/city-state/`)
3. If "Fetch From Anywhere" is enabled, includes all pages; otherwise, only location pages
4. Crawls each page at a rate of **1 URL per second maximum**
5. For each page, extracts all `<img>` tags and background images
6. Filters images by minimum width of **720 pixels**
7. Selects up to the user's specified images-per-page target, prioritizing larger/higher-quality images
8. Runs **perceptual image hashing** across the entire batch to detect duplicates (90%+ similarity = duplicate, skip it)
9. Infers location names from page URLs and page content

**Location inference logic:**
- Extract city/region from URL slug (e.g., `/locations/naperville/` → "Naperville")
- Resolve ambiguous locations (e.g., "Springfield" could be in 30+ states) by examining the broader context: other locations already identified for this website, business address in the site footer, state abbreviations on other pages
- If still ambiguous, make an AI API call to resolve
- Display inferred location on each row with an edit option so the user can correct

**When crawl completes, the user sees:**
- A summary table with one row per location page
- Each row shows: location name (editable), images found vs. target, thumbnail strip of candidates
- Rows with zero qualifying images get a warning indicator
- Images from non-location pages (when "Fetch From Anywhere" is on) appear in an "Unassigned" group for manual location tagging or AI suggestion
- A collapsed "Skipped Duplicates" section at the bottom shows what was removed

**Graceful degradation:** If a page yields fewer qualifying images than the target (e.g., user asked for 3 but only 1 meets the quality bar), that's fine. Show what was found. Quality over quantity. If a page yields zero qualifying images, flag it but don't block the workflow.

**For manually uploaded images:** They appear in the same table view, either pre-tagged with keyword/location (if the user tagged them during upload) or in the "Unassigned" group.

### Stage 3: Keyword Matching

The app analyzes each selected image using the Gemini 2.5 Flash vision API to classify its content, then matches it to the best keyword from the user's list.

**Image analysis pipeline:**
1. For each image, check if `max(width, height) > 768`. If yes, create a resized copy where the larger dimension is 768px (maintaining aspect ratio). If no, use the image as-is.
2. Send the (possibly resized) image to Gemini 2.5 Flash with the keyword list and a classification prompt
3. Gemini returns the best-matching keyword and a confidence score
4. Original high-res image is preserved for overlay processing — the resize is only for the API call

**UI for keyword matching:**
- Images are grouped by their detected content category
- Example: "12 images classified as kitchen scenes — suggested keyword: Kitchen Remodeling"
- The user confirms or changes the keyword per group, not per individual image
- Images where Gemini couldn't confidently match a keyword are separated into a "Needs Attention" section for manual assignment
- If the user pre-assigned keywords during upload, those images skip this step

### Stage 4: Preview & Confirm

Before batch processing, the app generates up to **10 preview images** with overlays applied.

**Preview selection strategy:** Don't just show the first 10. Pick strategically:
- One from each content category
- Prioritize images where overlay placement might be tricky (high visual complexity, unusual aspect ratios, very dark or very light images)
- This gives the user a representative sample of the hardest cases

**Each preview card shows:**
- The image with overlay applied at the AI-recommended position
- A placement toggle (top-left, top-center, top-right, bottom-left, bottom-center, bottom-right)
- A text size slider
- A "Regenerate" button that tries an alternative placement

**Below the previews:**
- A collapsed section listing all other images with their source URLs, assigned keywords, and assigned locations for spot-checking
- The user can expand this to verify assignments without generating full previews for every image

**Overlay placement algorithm:**
The app evaluates candidate overlay positions and scores each on two criteria:
1. **Readability:** Contrast between the text and the underlying image region. The translucent background bar helps, but placement in a region with more uniform luminance is still preferable.
2. **Subject preservation:** Avoid placing the overlay over the main subject of the image. Use visual saliency analysis to detect where the "interesting" parts are and place the overlay elsewhere.

The winning position is applied automatically. The user can override on previews.

### Stage 5: Generate & Download

The user hits "Generate All" and the app processes the entire batch asynchronously.

**Progress UI:**
- A counter: "Processing 47 of 156 images"
- A progress bar
- A live feed of completed image thumbnails scrolling in as they finish
- The user can leave and come back — the session persists

**Output:**
- A ZIP file containing all processed images
- Filenames follow the convention: `location-keyword-original-filename.jpg` (or similar clean format)
- A `manifest.csv` file inside the ZIP mapping each filename to its location, keyword, source URL, and overlay position used
- The ZIP download link appears when processing completes
- The link is added to the user's download history

---

## 3. Download History

Accessible from the app's navigation. Shows all past projects for this session.

| Column | Description |
|---|---|
| Date | When the batch was generated |
| Client Name | As entered in project setup (or "Untitled" if blank) |
| Image Count | How many images were in the batch |
| Download Link | Active for 24 hours, then shows "Expired" |

- Session is identified by a browser cookie that persists for **180 days**
- ZIP files are stored on the Railway volume and deleted after **24 hours** via a cleanup job
- Download history metadata persists in PostgreSQL for the life of the cookie, even after files expire

---

## 4. Overlay Specifications

### 4.1 Text Content

Always two lines:
- **Line 1 (top):** Keyword (e.g., "Kitchen Remodeling")
- **Line 2 (bottom):** Location (e.g., "Naperville, IL")

### 4.2 Font Options

Nine Google Fonts, downloaded and bundled with the app (no external requests at render time):

1. **Montserrat** — Clean, modern all-rounder. Default choice.
2. **Poppins** — Geometric, friendly. Tech, cannabis, e-commerce.
3. **Oswald** — Condensed, bold. Construction, contractors.
4. **Roboto** — Neutral workhorse. Works everywhere.
5. **Playfair Display** — Elegant serif. Law firms, luxury brands.
6. **Lato** — Warm, approachable. Service businesses.
7. **Bebas Neue** — Bold display. Maximum impact.
8. **Raleway** — Stylish. Lifestyle brands, boutiques.
9. **Nunito** — Rounded, friendly. E-commerce, family businesses.

The user selects one font per project.

### 4.3 Overlay Visual Design

- A **translucent background bar** behind the text for readability
- Bar color and opacity adapt based on the underlying image region (dark bar on light regions, light bar on dark regions)
- Text color contrasts with the bar (white text on dark bar, dark text on light bar)
- Text size scales relative to image dimensions but stays readable
- Keyword line is slightly larger/bolder than the location line

### 4.4 Placement Logic

The app automatically determines the best position from these candidates:
- Bottom-center (most common default)
- Top-center
- Top-left
- Top-right
- Bottom-left
- Bottom-right

Selection is based on:
1. **Readability** of text against that region
2. **Subject preservation** — avoiding the main focal point of the image

The user can override placement on preview images.

---

## 5. Image Handling Rules

### 5.1 Minimum Quality

- Width must be at least **720 pixels**
- Images below this threshold are skipped during crawling

### 5.2 Deduplication

- Use perceptual image hashing (e.g., `imagehash` library with average hash or difference hash)
- Images with **90%+ similarity** are considered duplicates
- Keep the first instance, skip subsequent duplicates
- Show skipped duplicates in a collapsed UI section

### 5.3 Supported Formats

- JPEG, PNG, WebP as input
- Output as JPEG (good balance of quality and file size for GBP uploads)

### 5.4 Image Resizing for AI Classification

- If `max(width, height) > 768px`, resize so the larger dimension = 768px, maintaining aspect ratio
- This resized copy is used **only** for the Gemini API call
- The original image is always used for overlay rendering

---

## 6. Sitemap Crawling Rules

### 6.1 Rate Limiting

- Maximum **1 URL per second** when crawling a client website
- No parallel requests to the same domain

### 6.2 Location Page Detection

The crawler identifies location pages by URL patterns such as:
- `/locations/city-name/`
- `/service-area/city-state/`
- `/areas-we-serve/city/`
- `/city-name/` (if it matches a known city pattern)

Also check the sitemap XML itself for image entries (`<image:image>` tags) which may provide direct image URLs.

### 6.3 "Fetch From Anywhere" Mode

When enabled:
- All pages in the sitemap are eligible for image scraping
- Images from location pages still get their location association
- Images from non-location pages (home page, gallery, blog, etc.) are placed in an "Unassigned" group
- The app uses AI to suggest locations for unassigned images, or the user assigns them manually

### 6.4 JavaScript-Rendered Sites

- Default scraping uses HTTP requests + HTML parsing (fast, lightweight)
- A checkbox option "JS-rendered site" enables headless browser scraping via Playwright for sites that load images via JavaScript
- This option is off by default and should only be used when standard scraping fails to find images

---

## 7. Session & Storage

### 7.1 Session Model

- No login or accounts
- Session identified by a browser cookie
- Cookie lifetime: **180 days**
- All download history and project metadata tied to the session cookie

### 7.2 File Storage

- Processed ZIP files stored on Railway persistent volume
- A cleanup job runs periodically and deletes ZIP files older than **24 hours**
- If storage becomes tight, the retention window can be reduced to 6 hours
- Download history metadata in PostgreSQL persists even after files are deleted (links show as "Expired")

---

## 8. API & External Dependencies

### 8.1 Gemini 2.5 Flash

- Used for image content classification and keyword matching
- API key stored as Railway environment variable (no UI management)
- Rate limit: stay at **90% of Gemini's maximum API rate limit** to avoid hitting caps
- Cost estimate: ~$0.04 per 1,000 images at 258 tokens per image (when images are resized below 768px threshold)

### 8.2 Gemini for Location Resolution

- When location names are ambiguous (e.g., "Springfield" with no state), use a Gemini text call with context from other identified locations to resolve the full location name
- These are lightweight text-only calls with minimal token usage

---

## 9. Scale & Performance

### 9.1 Expected Workload

- Typical project: 50-200 images
- Large project: up to 300+ images
- Maximum crawl: 200+ location pages

### 9.2 Async Processing

- Image crawling, classification, and overlay generation all run as background tasks
- Frontend displays a live progress bar and thumbnail feed
- The user can navigate away and return — progress is tied to the session

### 9.3 Concurrency

- Crawling: sequential (1 URL/second) to avoid overloading client sites
- Gemini API calls: up to 15-20 concurrent requests (within 90% of rate limit)
- Overlay rendering: parallel processing using Python multiprocessing or thread pool

---

## 10. Non-Goals (For Now)

These are explicitly out of scope for the initial version:

- **User accounts / login** — session-based only
- **Error recovery / single-image re-processing** — user must regenerate full batch
- **Multiple overlay variants per image** — one overlay per unique image
- **GBP direct upload integration** — user downloads the ZIP and uploads manually
- **Custom fonts** — limited to the 9 bundled Google Fonts
- **Video processing** — images only
- **Multi-language UI** — English-only interface (overlay text can be any Unicode language)

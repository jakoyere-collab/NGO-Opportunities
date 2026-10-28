# Video Production & Publishing Guide

A repeatable checklist for turning a script in `docs/scripts/` into a published video on the [NGO Opportunities YouTube channel](https://www.youtube.com/@NGO-Opportunities).

## 1. Generate the video

- Use an AI avatar tool — HeyGen is the current pick for this channel (see walkthrough below); Synthesia is a solid alternative if you prefer its enterprise/training-oriented feature set. A stock-footage-plus-voiceover tool (Pictory, InVideo) works too if you prefer that style.
- Feed in each scene's voiceover line and on-screen text from the script.
- Add the logo as a burned-in watermark (see below) as part of the export, not as an afterthought.
- Export vertical (9:16) to be Shorts-eligible, or horizontal (16:9) for a standard long-form upload.

### HeyGen walkthrough (first-time setup)

1. Sign up at heygen.com. The free plan is watermarked and capped at a few short videos a month — go with the **Creator** plan (check current pricing on their site, it changes) if you want the watermark removed and enough monthly minutes to cover 2–3 videos a week.
2. Set up your **Brand Kit** (look for "Brand Kit" in the sidebar or workspace settings — HeyGen has moved this before, so check nearby menus if it's not where you expect): upload your logo (`assets/logo.png`) and set brand colors — navy `#0A2A43`, blue `#1E6FB8`, green `#3FA34D`, orange `#F2994A` (from `styles.css`). One-time setup, benefit forever.
3. Create new video → **Avatar video** project.
4. Pick a stock avatar with a professional, approachable tone matching the channel (no need to clone your own face/voice for this use case).
5. Pick a voice from HeyGen's voice library and language (English); the Voice Director controls let you tune pacing/tone if the default read feels off.
6. Build scenes one at a time, mapping directly onto the script structure:
   - Scene 1 = the script's **Hook** line.
   - One scene per numbered *Scene* in the script — paste that scene's *Voiceover* line into the script box (the avatar reads it aloud).
   - Add the script's *On-screen text* as a text overlay on that same scene.
   - For *Visual suggestion*, either pick a matching stock background/video from HeyGen's library or upload your own image for that scene.
7. Repeat for the **Call to action** as a final scene.
8. Preview the whole thing scene-by-scene: check lip-sync, timing, that captions aren't cut off, and that the avatar's pacing feels natural.
9. Confirm your logo shows on every scene (via Brand Kit) — if it isn't applied automatically, check that scene's branding toggle.
10. Generate/Export the video — rendering takes a few minutes depending on length.
11. Download the MP4, then work through the upload checklist below (title, description, thumbnail, playlist, Public visibility).

Start with `docs/scripts/cv-01-the-6-second-cv.md` — it's already broken into exactly this scene structure.

## 2. Watermark — always both layers

1. **Burned into the export** (in the video tool itself): logo as an image overlay for the entire timeline, small, bottom-right corner, semi-transparent. This is what stays with the file even if it's downloaded or reposted elsewhere — the durable brand mark.
2. **YouTube channel watermark** (one-time setup, applies to every future video automatically): Studio → Customization → Branding → Video watermark → upload the logo → display time **"Entire video."** Doubles as a clickable subscribe button. This only renders inside YouTube's own player, so it doesn't replace #1.

## 3. Upload checklist

- **Title**: the script's `TITLE:` line.
- **Description**: the script's `WHATSAPP CAPTION` line + hashtags, plus a link to `https://ngoopportunities.com/opportunities/`.
- **Thumbnail**: custom, not auto-generated — logo + a short title phrase (Canva is fine for this).
- **Playlist**: one per content-plan category (CV Writing, Cover Letters, Interview Prep by Stage, Interview Simulation, NGO Career Tips, Career Growth & Development) — create these once, add every new video to its category playlist.
- **Audience**: "No, not made for kids."
- **Visibility**: Public.

## On download protection — set expectations honestly

No video that streams to a browser is fully un-downloadable, YouTube included — there's no per-creator DRM control on regular uploads, only inside YouTube's own Premium offline-download feature. Realistic options:
- Disabling embedding (Advanced settings) stops other *sites* embedding the player — it doesn't stop ripping.
- Locking a video down (unlisted/members-only) cuts your own reach into the WhatsApp community far more than it stops a determined downloader — usually not worth it for this series.
- The burned-in watermark above plus YouTube's copyright takedown tool (available to any channel, for content reposted elsewhere) is the realistic, available protection — deterrence and attribution, not prevention.

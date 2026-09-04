# 28: Onboarding for a new profile

**What to build:** A new profile opens with a short onboarding instead of an empty chat. The user picks which categories exist for them (the default taxonomy with subcategories shown as toggles, each category on or off, plus adding their own and renaming), sets the few preferences that shape the assistant (answer language: follow my message, German, or English; default model; web lookup on or off with its one-line privacy note), and gets their first data in (drop a statement or CSV here, which hands the file to a new chat where import and the Question cards happen, or load the shipped sample year to try things out). Finish lands in a chat with a short welcome that says what to ask first. Onboarding is skippable at every step, resumable, and reopenable from Settings. Requested by the user on 2026-09-05.

**Blocked by:** 24 (merged)

**Status:** ready-for-agent

- [ ] Profile gains an onboarding state (not started, done, skipped); the first profile created at startup and every new profile start in not started; the app opens onboarding for a profile in that state and never again once done or skipped, with a Settings entry to reopen it
- [ ] Step 1 Categories: the default taxonomy rendered as a toggle list with subcategories underneath, all on by default; the user turns categories off (they are removed from this profile's taxonomy), adds a category or subcategory, renames inline; Needs review and Unknown are explained in one line and are not toggles
- [ ] Step 2 Preferences: answer language (follow my message, German, English) stored on the profile and read by the prompt; default model slot for new conversations; web lookup switch with the privacy note (only a scrubbed merchant token ever leaves, off by default)
- [ ] Step 3 First data: a drop zone that accepts CSV, PDF and images and hands them to a new conversation exactly like dropping into the composer (so import, mapping confirmation, duplicates and Question cards all happen in chat), or a "Load the sample year" button that imports the shipped synthetic dataset through the same path, or Skip
- [ ] Finish: a new conversation opens with a short welcome message seeded by the server (no model call), naming the profile's data state and three things to ask first
- [ ] Skip and Back on every step; state saved per step so a reload resumes; keyboard reachable
- [ ] Copy is plain and short; both themes; 1024 and 1440; the flow uses the shadcn and AI Elements primitives already in the app and follows the repo skills
- [ ] HTTP-seam tests: onboarding state transitions, taxonomy toggles remove and add categories, preferences stored and read by the prompt (language rule), sample data import through the chat path, welcome turn seeded; typecheck, build and suite green; browser verification of the full flow in both themes

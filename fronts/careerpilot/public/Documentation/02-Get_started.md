# Get Started

## Step 1: Teach CareerPilot about you

The first thing CareerPilot needs to do is learn about you. To match you with jobs, tailor your resume and tune your job search, its agents need your work history, education, projects and achievements.

CareerPilot keeps all of this in one file, your **knowledge base** (`Docs/user_docs/user_knowledge.md`). The CareerPilot agent writes it from documents you give it, and the other agents read it:

- **Qualification check** scores each job posting against it.
- **Resume builder** writes tailored resumes from it.
- **Portal search** uses it to decide which job titles and companies to look at.

With one short, organized summary to read, the agents don't have to dig through every resume and write-up you own, so they work faster and give better results.

### Add your documents

Put your files in the `Docs/user_docs/` directory. The agent reads **PDF**, **Markdown (`.md`)** and **plain text (`.txt`)** files. Sort them into these folders:

| Folder | What to put there |
| --- | --- |
| `workexperience/` | Your resumes. Several versions are fine; where they disagree, the newest wins. |
| `education/` | Transcripts, diplomas and certificates. |
| `projects/<name>/` | One folder per side project, with its write-up or report. Images and other files are ignored. |
| `papers/` | Papers you wrote or co-wrote. |
| `achievements/` | Hackathons, competition results, awards and scholarships. |
| `Docs/user_docs/` itself | Anything else, such as a bio or a LinkedIn export. |

For example:

```
Docs/user_docs/
├── workexperience/
│   └── resume_2026.pdf
├── education/
│   └── transcript.pdf
├── projects/
│   ├── careerpilot/
│   │   └── README.md
│   └── trading-bot/
│       └── report.pdf
├── papers/
│   └── my_paper.pdf
└── achievements/
    └── hackathons.md
```

You don't need every folder. Start with your resume and add more whenever you like.

### Keeping it up to date

The knowledge base is never rewritten from scratch. Each time it is generated, the agent starts from the current version and adds what your documents say, so:

- Facts you typed into `user_knowledge.md` yourself are kept.
- Facts from documents you have since deleted are kept.
- The previous version is saved as `user_knowledge.prev.md` in case you want to go back.

When something changes, like a new project, a new resume or a new award, drop the file in its folder and update the knowledge base (see Step 2).

## Step 2: Generate your knowledge base

1. Click **Knowledge** in the navigation bar.
2. If any folders are missing, the page lists them. Click **Create them** to set them up in `Docs/user_docs/`, then add your files.
3. Under **What are you providing?**, tick the kinds of documents you added, then click **Refresh**. The page checks each ticked folder and warns you about any that are still empty.
4. Optional: leave **Also tune the job search** ticked to let the agent update `portals.yml`, the job titles to look for and to skip, and which companies to track. Companies it drops are disabled, not deleted.
5. Click **Generate knowledge base**. Once you have one, the button says **Update knowledge base**.

You can follow the agent as it works through each section. When it finishes, the page shows your new knowledge base and any changes it made to `portals.yml`. If it added companies, check that their careers page URLs in `portals.yml` are right.

Read through the result. If anything is wrong or missing, fix the source document and update again, or edit `user_knowledge.md` directly. Your edits are kept on the next update.

## Optional: Connect Google Drive

The Resume Builder can save your resumes to your Google Drive as Google Docs (see Build a Resume). You can skip this: everything else works without it, and you can always copy or download your resumes as Markdown.

There's nothing to set up ahead of time. The first time you click **Save to Drive**:

1. A Google sign-in window opens.
2. Pick your Google account and click **Allow**.
3. The window closes by itself and your resume is saved.

From then on, **Save to Drive** saves right away. CareerPilot keeps the sign-in on your computer (`Docs/google/token.json`, never committed to git), so you stay connected after a restart.

CareerPilot only gets access to the files it creates itself. It can't see or change anything else in your Drive.

- **See which account is connected** at the top of the Resume Builder's **Editor** tab, next to the draft list.
- **Disconnect** with the **Disconnect** link next to it. Docs you already saved stay in your Drive.
- **If the sign-in window doesn't open**, your browser blocked it. Allow popups for CareerPilot and click **Save to Drive** again.
- **If Google warns "Google hasn't verified this app"**, click **Advanced**, then **Go to CareerPilot**. CareerPilot is open source and only asks for access to its own files.

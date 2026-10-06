# Build a Resume

Once your job search has saved some jobs (see Search for Jobs), CareerPilot can write a resume tailored to each one. Click **Resume** in the navigation bar to open the Resume Builder.

For the job you pick, the Resume Builder agent writes two documents:

- **Resume**: a one-page resume in Markdown. It leads with the experience, projects and skills that match the posting, and uses the posting's wording where it truthfully describes your work.
- **Side projects**: the posting's requirements you have no evidence for yet, and 2–3 side projects that would close those gaps. Each project lists its stack, its milestones and the resume bullet you could add once it is done.

Both are written only from your knowledge base and your project write-ups (`Docs/user_docs/projects/`). The agent never invents employers, titles, dates, degrees, skills or numbers. If something is missing from your resume, add it to your knowledge base first.

The page has three columns: your **saved jobs** and their drafts on the left, the **document** in the middle, and the **Resume assistant** chat on the right.

## Step 1: Pick a job

The **Saved jobs** list shows every job on your job board, best match first. The number next to each job is its match score out of 10.

- **Find a job** by typing a company or position in **Filter jobs**.
- **Pick a job** by clicking it. The header shows its company, position and match score.

If the list is empty, click **Go to search** and run a job search first.

> **Tip:** Jobs scoring 5–8 are often the best ones to tailor for. You have the background, and a tailored resume and a side project or two can close the gap.

## Step 2: Build a resume

Click **Build resume**. The status at the top right shows how long the build has been running. It usually takes a minute or two, because the agent runs on a language model on your own computer.

When it finishes, the new draft opens on the **Resume** tab.

Each job can have several drafts. To start over from scratch, click **Build a new draft**: your earlier drafts are kept. They are listed under **Drafts for this job**, with the most recently edited one at the top. Click a draft to open it.

## Step 3: Read and export the documents

Switch between the two documents with the **Resume** and **Side projects** tabs. The buttons above the document:

| Button | What it does |
| --- | --- |
| **Posting** | Opens the original job posting in a new tab, so you can compare. |
| History (clock icon) | Shows the earlier versions of this draft. The number is how many there are. See Step 5. |
| **Edit** | Lets you edit the open document by hand. |
| Copy | Copies the open document's Markdown to the clipboard. |
| Download | Saves the open document as a `.md` file named after the company and position. |

The documents are Markdown, so you can paste them into any editor that reads Markdown, or convert them to PDF or Word with a tool such as Pandoc.

## Step 4: Refine it with the Resume assistant

The **Resume assistant** on the right edits the open draft for you. Type what you want changed and press **Enter** (**Shift+Enter** adds a new line). For example:

- "Make the summary shorter and punchier"
- "Add my StockMarket project"
- "Emphasize my Kubernetes and MLOps work"
- "Which skills from the posting am I missing?"

On a new draft, these appear as suggestions you can click.

The assistant replies in a sentence or two. If it changes a document, you can watch the new version being written into it, and the tab being changed shows a pulsing dot. It only changes what you ask for, and it keeps the resume to one page. If you only ask a question, the documents are left as they are.

The assistant follows the same rule as the builder: it only uses facts from your knowledge base, your project write-ups and the current draft. If you ask for something they don't support, it tells you instead of making it up. When you mention a project or a topic by name, the assistant reads that part of your knowledge base and the project's full write-up, so naming things helps.

The chat history is saved with the draft, and each draft has its own chat.

The badge at the top of the chat shows the connection to CareerPilot. If it isn't connected, the chat retries on its own. You can send a message once it is connected.

## Step 5: Edit by hand and go back to earlier versions

### Edit by hand

1. Open the **Resume** or **Side projects** tab.
2. Click **Edit**. The document becomes a Markdown text box.
3. Make your changes and click **Save**, or **Cancel** to throw them away.

You can't edit by hand while the assistant is writing a reply.

### Restore an earlier version

Every change to a draft, whether from the assistant, a manual edit or a restore, first saves the old content as a version. Click the history button to see them, newest first. Each one says what replaced it, for example the chat message that changed it.

Click **Restore** to bring a version back. Your current content is saved as a version first, so a restore can be undone too.

A version holds both documents, so restoring one brings back the resume and the side projects as they were at that time.

## Good to know

- **Only one agent runs at a time.** Building a resume and chatting both use the same local model as the job search, the Knowledge agent and Analytics. If another agent is busy, you'll see a message asking you to try again when it finishes.
- **Drafts don't update themselves.** A draft is a snapshot of your knowledge base when it was built. After you update your knowledge base, build a new draft, or ask the assistant to add what's new.
- **Better input, better resume.** The resume is only as good as your knowledge base and project write-ups. Write down your results and numbers there, and the agent will use them.
- **Check before you send.** The agent sticks to your facts, but read the resume through before you apply, especially your contact details, dates and job titles.

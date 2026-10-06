# Analyze Your Search

Once your job search has saved some jobs (see Search for Jobs), CareerPilot can show you how your search is going. Click **Analytics** in the navigation bar to open the Analytics page.

The page has two parts:

- **Charts** of every job on your job board: how far your applications get, how well the jobs match you, and which companies and work types lead to interviews. They are always up to date and need no AI.
- **AI insights**, which the Analytics agent writes when you ask it to: a written review of your search, the near-miss jobs you almost qualify for, the skills they ask for that you're missing, and side projects that would close those gaps.

If you haven't saved any jobs yet, the page asks you to run your first search. Click **Go to search** to start one.

## The numbers at the top

Four tiles sum up your search:

| Tile | What it shows |
| --- | --- |
| Jobs found | Every job on your job board. |
| Applied | Jobs you applied to, and their share of all jobs found. |
| Interviews | Jobs where you got an interview, and their share of all jobs found. |
| Avg. compatibility | The average match score of all your jobs, out of 10. |

These numbers come from the **Status** you set on each job in the Search page's **Results** tab. Keep your statuses up to date and the charts stay accurate.

A job counts as **applied** once its status is Applied, any Interview status or Denied, since you can only be turned down after you apply. It counts as an **interview** once its status is Interview Scheduled, Interview Inprogress or Interview Done.

## Pipeline tab

The **Pipeline** tab shows how far your jobs get, and when.

- **Funnel**: how many jobs reached each stage: Found, Applied, Interview and Interview done. Each bar shows the count and its share of all jobs found.
- **Weekly activity**: jobs grouped by the week they were last updated, colored by their status: Found only, Applied, Interviewing, and Dropped / denied. A job appears once, in the week of its latest change, so a job you found in one week and applied to the next is counted in the second week.

Hover over a bar to see its exact numbers.

## Fit & companies tab

The **Fit & companies** tab shows how well your jobs match you and where your applications go.

- **Compatibility**: how many jobs got each match score from 0 to 10, next to how many of them you applied to. The shaded 5–8 band is where near-miss jobs are (see AI insights). If you only apply to 9s and 10s, the near-miss jobs may be worth a second look.
- **Work type**: found, applied and interviewed jobs for onsite, hybrid, remote and unknown roles.
- **Top companies**: the 10 companies with the most jobs on your job board, with how many you applied to, how many led to an interview, and their average match score.

## AI insights tab

### Run the analysis

Click **Run AI analysis**. The page switches to the **AI insights** tab, and the status at the top right shows how long the agent has been working. It takes a few minutes.

The Analytics agent works like a data analyst. It reads every job, including its description and the Qualification agent's breakdown of the skills you have and the skills you're missing, along with your knowledge base and project write-ups. Then it writes and runs Python code in a **sandbox**, a separate container that can't touch the rest of your computer, until its results are complete. The sandbox runs in Docker, so Docker must be running.

You can leave the page while it works. When you come back, the page picks up where it was. When the analysis is done, the button changes to **Re-run AI analysis**. Run it again whenever you've saved more jobs or updated your statuses.

### What you get

**Conclusion and analysis.** The conclusion box gives the main takeaway and your next steps in a few sentences. Below it, one or two paragraphs explain how far your jobs get through the funnel, which companies, work types and match scores lead to applications and interviews, how your activity changed over the weeks, and what the near-miss jobs have in common.

**Near-miss jobs.** These are jobs with a match score from 5 to 8 that are missing at least one **required** skill. You have the general background, but a few crucial skills are missing. The number next to the **AI insights** tab name is how many there are. For each job, the table shows:

| Column | What it shows |
| --- | --- |
| Role | The position and company. |
| Compatibility | The match score out of 10. |
| Status | Where you are with this application. |
| Missing required skills | The required skills from the posting that your knowledge base doesn't show. |
| View | Opens the original posting in a new tab. |

**Skill gaps.** A chart of the skills the near-miss jobs ask for that you don't have, up to 10, most important first. **Missing in** is how many near-miss jobs list the skill, and **Required in** is how many of those list it as required, not just preferred. The agent merges different spellings of the same skill, such as "k8s" and "Kubernetes". Hover over a bar to see which companies ask for it.

The skills that are required by the most jobs are the ones worth learning first.

**Side projects to close the gaps.** 3–5 project ideas that together cover your top skill gaps. Each card shows:

- the **skills** it covers, from the skill gaps chart.
- **what to build**.
- **Why**: the near-miss jobs or companies it helps with.
- the **effort**: a weekend, 1–2 weeks, or 1 month+.

The projects build on what your knowledge base shows you already know, and the agent won't suggest a project you've already done.

> **Tip:** To go from a near-miss job to an application, open the Resume Builder, pick the job and build a resume. Its **Side projects** tab gives you project ideas for that one job.

## Good to know

- **Only one agent runs at a time.** The Analytics agent uses the same local model as the job search, the Resume Builder and the Knowledge agent. If another agent is busy, you'll see a message asking you to try again when it finishes.
- **The charts and the AI insights can differ.** The charts always show your job board as it is now. The AI insights show it as it was when you last ran the analysis. Re-run it to bring them in line.
- **Insights only use your facts.** A skill counts as missing if your knowledge base doesn't show it. If a skill you have shows up as a gap, add it to your knowledge base. Jobs found after that are scored with it. Jobs already on your job board keep their old scores until they are saved again, for example by adding the job by hand in the Search page.
- **If something goes wrong,** a warning appears at the top of the **AI insights** tab, and the charts keep working. A common cause is that Docker isn't running, so the sandbox can't start.
- **Insights are kept until the backend restarts.** The latest analysis is stored in memory and remembered by your browser. If you restart the backend or open the page in another browser, run the analysis again.

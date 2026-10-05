# Search for Jobs

Once your knowledge base is ready (see Get Started), CareerAI can look for jobs for you. Click **Search** in the navigation bar to open the job search page. Each search runs three agents, one after another:

1. **Search**: the Portal Search agent visits each company careers page you track and collects its open positions.
2. **Qualify**: the Qualification Check agent reads each new posting, lists its technical requirements, compares them to your knowledge base and gives the job a match score from 0 to 10.
3. **Ingest**: CareerAI saves the scored jobs to your job board, so you can track your applications.

The page has three tabs: **Overview** sets what to search for, **Search** runs the search, and **Results** shows the jobs it saved.

## Step 1: Choose where and what to search

Open the **Overview** tab. It has two lists, both stored in `portals.yml`.

### Portals

Portals are the company careers pages the search agent visits.

- **To add one**, type the company name and the URL of its careers page (it must start with `http://` or `https://`), then click **Add**.
- **To remove one**, hover over it and click the trash icon. The company is disabled in `portals.yml`, not deleted, so you can add it back later.

Careers pages hosted on Greenhouse, Lever or Ashby work best, because the agent can read their job data directly. Other pages work too, but the agent has to read the page itself, which is slower and less reliable.

### Target positions

Target positions are keywords for the job titles you want, such as `machine learning engineer` or `ai platform`.

- **To add one**, type the keyword and click **Add**.
- **To remove one**, hover over it and click the trash icon. You must keep at least one.

You can't edit either list while a search is running. Wait until the search finishes.

> **Tip:** When you generate your knowledge base with **Also tune the job search** ticked, the Knowledge agent fills in both lists for you. Use this tab to fine-tune them.

## Step 2: Run a search

Open the **Search** tab.

1. **Pick the portals.** Click **Portals** to see the list. All enabled portals are ticked by default. Untick the ones you want to skip for this run, or use **Select all** and **Clear**.
2. **Add a position by hand (optional).** Maybe you found a job somewhere else, such as on LinkedIn or a referral. To have CareerAI score and save it, click **Add position** and fill in the form:

   | Field | What to enter |
   | --- | --- |
   | Company | The company's name. |
   | Position | The job title. |
   | Link | The URL of the posting. |
   | Job type | Onsite, hybrid, remote or unknown. |
   | Post id | Optional. The posting's ID on the job board. |
   | Description | The full job description. Paste all of it: the Qualification agent scores the job from this text. |

   Click **Queue position**. The position appears under the portal list and is processed by the next search. To remove it before then, click the **×** next to it. You can queue several positions, and you can run a search with only manual positions and no portals.
3. **Click Run search.** The status at the top right of the page shows the search is running.

### Follow the search

While the search runs, the page shows its three stages: **Search**, **Qualify** and **Ingest**. Each one has a live log below it.

- **Search log**: each portal as it is searched and how many postings it returned. Jobs already on your job board are skipped, so each posting is only scored once.
- **Qualify log**: each posting as it is scored, with its score out of 10.
- **Ingest log**: how many jobs were saved.

Errors appear in red, and each log's header shows how many there were. One failed portal or posting doesn't stop the search, so the rest still get processed.

If the search finds no new postings, the **Qualify** and **Ingest** stages are marked **Skipped**.

Searching can take a while, because the agents run on a language model on your own computer. Each portal and each posting takes its own turn. You can leave the page and come back: the search keeps running, and the page shows its progress when you return.

When the search is done, the page shows how many jobs were saved and how many were skipped because they were already saved. Click **View results** to see them.

## Step 3: Review your results

The **Results** tab lists every job on your job board. The number next to the tab's name is the total.

| Column | What it shows |
| --- | --- |
| Company | The company's name. |
| Position | The job title, with its post id if it has one. |
| Type | Onsite, hybrid, remote or unknown. |
| Match | How well the job fits your profile, from 0 to 10. |
| Status | Where you are with this application. You can change it. |
| Updated | When the job was last saved or changed. |
| ↗ | Opens the original posting in a new tab. |

- **Search** for a company or position with the search box.
- **Filter** by status with the dropdown next to it.
- **Sort** by Company, Match or Updated by clicking the column's name. Click it again to reverse the order.

### What the match score means

| Score | Meaning |
| --- | --- |
| 9–10 | You meet nearly all the required skills and most of the preferred ones, and the seniority fits. |
| 7–8 | You meet most required skills. The gaps are small or quick to learn. |
| 5–6 | You meet about half the required skills, or the job is more senior than you. |
| 3–4 | You are missing major core skills. |
| 0–2 | The job is in a different field or far more senior than you. |

A skill only counts as a match if your knowledge base shows it, through your work experience, projects, coursework or skills. If a score looks too low, check that your knowledge base mentions everything you know, then update it.

Jobs in the 5–8 range are often near-misses: you have the background, but a few skills are missing. The Resume Builder and Analytics agents help you close those gaps.

### Track your applications

Use the **Status** dropdown on each row to track your progress. New jobs start as **Searched**.

| Status | Use it when |
| --- | --- |
| Searched | The search found the job. You haven't acted on it yet. |
| Applied | You sent your application. |
| Interview Scheduled | You have an interview coming up. |
| Interview Inprogress | You are in the middle of the interview rounds. |
| Interview Done | You finished interviewing and are waiting for an answer. |
| Denied | The company turned you down. |
| Drop | You decided not to pursue the job. |

Your changes are saved right away. The Analytics agent uses these statuses to chart your job search.

## Good to know

- **Only one agent runs at a time.** If another agent is busy (for example, the Knowledge agent is generating your knowledge base), wait for it to finish before you start a search.
- **Your statuses are kept.** Each job is identified by its link. If the same job is saved again, for example after you add it by hand, its details and score are updated, but its status stays as you set it.
- **Postings without a description aren't saved.** The Qualification agent can't score a job without its description, so the job is left out. The Qualify log lists these postings.
- **Job descriptions are saved as files.** Each saved job's full description is in `Docs/job_descriptions/`, where the Resume Builder can read it.
- **Don't restart the backend during a search.** A restart stops the search and clears its log. Jobs are only saved in the last stage, so a search that is stopped early saves nothing and you'll need to run it again. Jobs from earlier searches stay on your job board.

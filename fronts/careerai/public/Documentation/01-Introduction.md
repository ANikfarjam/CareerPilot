# Introduction

CareerAI, created by Ashkan Nikfarjam, is an open-source, AI-powered assistant for finding jobs and managing the application process. You don't have to search several job boards by hand and keep track of applications in a spreadsheet. CareerAI's agents find roles that match your skills, show you which ones you're really qualified for, and keep all of your applications in one place. The language model runs locally on your own hardware, so your personal data stays on your machine.

CareerAI is built from a set of specialized agents, and each one handles one part of the job search. 

* The **Portal Search** agent searches job-board APIs and collects openings that fit your profile. 
* The **Qualification Check** agent reads each job description, pulls out the key technical requirements, compares them to your background, and scores each job from 0 to 10. It also finds the near-miss jobs
(you have the general knowledge but miss some crucial skills) and recommends
side projects that close those skill gaps.

* The **Resume Builder** agent writes a resume tailored to a job you've saved. It also suggests side projects that would close any skill gaps. 
* Finally, the **Analytics** agent reviews the jobs you've searched, applied to, and interviewed for. It turns that history into charts and a short written summary, and it points out "near-miss" roles where only a few skills stand between you and a strong match.

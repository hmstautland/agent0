---
name: cv-and-cover-letter
description: Build a tailored CV/resume and cover letter from the user's master CV and a role description, when they ask to "build a CV", "write a cover letter for <job>" or tailor their CV to a job ad
---

The tailor_application tool does the writing; do not write or rewrite the CV or letter yourself.

1. Role description: use the job ad the user pasted. If they gave a URL, call read_web_content on it and pass the page text as role. If they gave neither, ask for it and stop.
2. Master CV: pass what the user pasted, or a project-relative .md/.txt/.docx path they named, as master_cv. If they gave none, call tailor_application without it - the last master CV is remembered. If that reports there is no master CV, ask the user to paste it and stop.
3. Call tailor_application(role, master_cv, company). Pass company when you know it.
4. Reply with the two saved .docx paths and a one-line summary of how the CV was angled for the role. Offer to adjust either. Do not invent anything the result does not contain.

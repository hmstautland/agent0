---
name: document-feature
description: After you added a new feature to the project (new tool, route, button, command), or when the user says yes to documenting a feature or asks to document one in docs/features
---

Only for new or changed things a user can do. Not for refactors, bug fixes, tests or styling.

If you just added the feature and the user has not answered yet:
- Do not write any docs. End your final answer with one question:
  "Do you want me to document this in docs/features/<name>.md?"
- If the user says no, do nothing more about it.

If the user said yes, or asked you to document a feature:
1. Call read_files with path docs/features/README.md to see the page layout and the index.
2. If a page for this feature already exists, read it and change it with edit_file.
   Otherwise create docs/features/<name>.md with write_file, using that layout.
3. Take names, settings and routes from the code (read_files), not from memory.
   Keep the page short and leave out sections with nothing in them.
4. Add a row for a new page to the table in docs/features/README.md with edit_file.
5. In your final answer, say which files you changed.

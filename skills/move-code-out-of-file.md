---
name: move-code-out-of-file
description: Move a block of code out of one file into another (e.g. inline <script> out of an HTML template into static/), extract, split or refactor code into a new file
---

- Never delete a block of code without first putting it somewhere else. Removing a
  <script> tag while leaving its code behind, or deleting the code entirely, is wrong.
- Decide the destination yourself, following the project layout (JavaScript belongs in
  static/, templates in templates/). Say which file you chose in your final answer.
- Write the destination file FIRST, then remove the block from the source.
- For "no scripts defined in the HTML, only loaded" style requests, use
  extract_inline_scripts - it moves the code and links it in one step.

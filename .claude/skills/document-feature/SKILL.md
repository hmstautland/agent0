---
name: document-feature
description: After a new user-visible feature has been added to agent0, or an existing one changed in a way users would notice (new tool, route, UI action, chat command, feature folder, skill, setting), ask the user whether to document it in docs/features/. Write or update the page only if they say yes. Also use when the user asks to document a feature. Skip refactors, bug fixes, tests and styling.
---

# Document a feature

`docs/features/` holds one page per feature, indexed in `docs/features/README.md`. The top-level `README.md` only links there.

## When to offer

Offer once the feature works, usually after its tests pass, when the change:
- adds something a user can do: a new registry tool, route/endpoint, UI button or dashboard, chat shortcut, CLI command, feature folder or skill, or
- changes how an existing feature is used: new options, settings or env vars, removed behaviour, or different limits.

Don't offer for refactors, bug fixes that don't change behaviour, test-only changes, styling, or internal renames. Don't offer again for a feature the user already said no to in this session.

## Ask first

Ask the user whether to document it, using AskUserQuestion if it's available. Name the page you'd write or update, e.g. "Document the new reminders feature in docs/features/reminders.md?" with options "Yes" and "No".

- **No:** do nothing. Don't write anything and don't bring it up again for this feature.
- **Yes:** follow the steps below.

## Writing the page

1. Read `docs/features/README.md` for the page layout and the index. If a page already covers this feature, update that page instead of adding a new one.
2. Write the page from the code as it is now, not from memory of the conversation. Check names, defaults, routes and env vars in the source.
3. Use the layout from the index: what it does, Using it, How it works (naming the main files), Settings, Limits. Leave out sections with nothing in them, and keep the page short.
4. Add or update the feature's row in the table in `docs/features/README.md`, and its bullet in the Features list in the top-level `README.md`.
5. If the feature changes how code should be edited, update `CLAUDE.md` too.
6. Tell the user in one line which files you changed.

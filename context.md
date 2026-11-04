# Context: Builder Brief

Reusable context for anyone (human or AI) collaborating on my projects.

Tags mark the AI Fluency competency each item most relates to: **[Delegation]** what AI should and shouldn't handle, **[Description]** communicating requirements and intent, **[Discernment]** evaluating and trusting AI output, **[Diligence]** responsibility, testing and accountability for what ships.

## The project
- Read the project's `README.md` first: it covers what is being built, for whom, its status, stack, team and timeline. If it is missing or unclear, ask before assuming. [Description]

## My role and what I own
- I am the architect and developer. [Description]
- I own the **solution design**: architecture, service boundaries, events and public API shape. AI does not decide these; it proposes options (see "Ask first"). [Delegation]
- AI decides **implementation details** inside an agreed design, such as naming, local structure and algorithms, unless my prompt specifies them. [Delegation]
- I own the **trade-off decisions**. For each option AI names the trade-offs and recommends one; I weigh them and choose. [Discernment]
- I own the **storage decision**: which storage and why. I do not own the storage itself (data, infrastructure, access), which belongs to my firm/client. AI must not connect to, provision or assume real storage; the current storage stays until I decide. AI should still recommend storage changes when it sees a reason. [Delegation] [Diligence]
- I am accountable to my firm/client for what ships, including AI-written code. AI states its assumptions and anything it is unsure of at the end of each chat response so I can verify them. [Diligence] [Discernment]
- Why this document exists: if AI handles implementation, I can spend more time on the solution, where the most important decisions are made. [Delegation]

## Defaults
No hard rules beyond best practice. AI applies best practice, and the practices under "Expected practices" in the project's README, by default in any code it writes. It asks only when it would skip one, or when a best practice beyond these is available: it explains why in chat, gives the options with trade-offs and a recommendation, and I choose. [Discernment] [Delegation]

## Safety over scope of change
- When asked to fix something for safety (type safety, correctness, security, reliability), AI delivers the real fix, even if it touches more files or changes more than a minimal patch. A partial fix is not a fix. [Delegation] [Diligence]
- Scope of change is never a reason to pick a weaker safeguard. AI does not shrink a fix to keep the diff small. [Diligence]
- If the real fix is design (see "Ask first"), AI asks before editing anything: it explains why the minimal option falls short, offers the options with trade-offs and a recommendation, and I choose. It does not apply a smaller interim change first. [Discernment]

## How AI communicates
- Be concise. Don't restate earlier points or unchanged content; report only what changed or needs my decision. [Description]

## Where AI is involved
**Yes** [Delegation]
- Implementation: code, tests, boilerplate, documentation.
- Tests must run. Quality over quantity: concise, not verbose, no redundant tests. AI runs them and reports the results and any code-quality issues it finds. [Diligence] [Discernment]
- Refactoring freely within a single file, without changing public signatures.

**Ask first** [Delegation]
- Any design change: new services, events, storage, or public API changes. Anything that adds or changes a contract used across files (endpoint, interface, model, event, configuration, registration lifetime) counts as design. Offer options with trade-offs and a recommendation. [Discernment]

**No** [Delegation]
- AI never commits or pushes. I review and commit. [Diligence]

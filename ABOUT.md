# ABOUT.md

## Why this role

I'm drawn to complex problems, and AI is shifting the frontier from "easy" engineering to genuinely hard ones. Using it well requires creativity, domain knowledge, and curiosity — not just prompting. I want to work with a team that takes that seriously and doesn't settle for mediocre outputs.

## How you work with AI tools

When working in an existing codebase, my instinct is to first ask the AI to sketch a summary of the project — or of the specific feature I'm touching — along with a list of its dependencies. From there I write pseudocode for the functions I need and ask the AI to implement them. I always ask the AI to write the tests too.

I trust the model for boilerplate, pattern-matching, and first drafts. I override it when it misses context, cuts corners on edge cases, or produces something that passes tests but doesn't fit the architecture. The judgment of when to accept vs. redirect is where most of the real work is.

## Your last project

**One ambiguity:** I had to decide whether to implement a new feature in the existing Clojure codebase — despite the ongoing migration — or build it in Python to stay aligned with the migration target. Since the migration was the primary goal, I leaned toward Python even though it added short-term complexity.

**One tradeoff:** Choosing Python meant I had to write migration scripts to move a complete DB schema from RDS to DynamoDB. It was time-consuming, but it kept us from deepening the Clojure dependency and paid off when the migration completed cleanly.

**One mistake:** I once failed to clearly communicate a new API contract to the frontend team, which caused a broken feature in production. It taught me to always document interface changes explicitly and confirm the other side has seen them before merging.

**One review comment:** The best review I received was early in my career — a detailed critique of the overall design structure of my solution. It made me always think about architecture before writing code, rather than jumping straight into implementation and cleaning up later.

## Anything you'd improve about THIS challenge or our CLAUDE.md

The challenge was more open-ended than I expected — which I appreciated. One idea: you could automate parts of this process using an AI interviewer that asks follow-up questions in real time, pushing candidates to defend their assumptions and adapt on the spot.

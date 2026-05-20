# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

**Brainiac** is a personal "second brain" knowledge base built from Markdown files. It is not a software project — there is no build system, no tests, no executable code. Future work in this repo will primarily consist of authoring, organizing, and transferring `.md` notes between memory directories.

Content language is **Brazilian Portuguese** (see `README.md`). Write notes in pt-BR unless the user asks otherwise.

## Memory model

The directory layout mirrors a cognitive-science model of human memory. Each top-level directory corresponds to a memory type and notes should be filed accordingly:

- **`longMemory/`** — Long-term retention. Information meant to persist indefinitely (years, lifetime).
- **`shortMemory/`** — Short-term / working memory. Transient notes (~20 seconds in the metaphor — in practice, scratch notes being actively worked on or rehearsed). Treat as a staging area.
- **`semanticMemory/`** — World knowledge / facts. Organized factual knowledge independent of personal experience (e.g., historical dates, definitions).
- **`memoryTransfer/`** — Promotion/demotion logic between the memories above. Referenced in `README.md` but **does not yet exist** as a directory; create it if/when transfer rules need to be encoded.

When the user adds a note, ask (or infer from context) which memory it belongs to rather than defaulting to one.

## Content convention: "tokenized" storage

`README.md` instructs that information be saved in a **token-optimized format** to make future searches and Claude interactions cheaper. Practical interpretation when writing notes:

- Prefer dense bullet points and short noun phrases over prose paragraphs.
- Strip filler words, articles, and redundant context that a future reader (human or LLM) can reconstruct from the surrounding note.
- Use consistent kebab-case or descriptive filenames so notes are greppable.
- Avoid duplicating the same fact across memory directories — instead, link by relative path.

This is the single most important repo-specific rule: terseness is a feature, not a style choice.

## Working in this repo

- Use the `Write` and `Edit` tools to create/modify `.md` files directly. No commands to run.
- This is **not** a git repository (verified via environment); do not attempt `git` operations unless the user initializes one.
- There is no README to keep in sync beyond the one already present — but if you significantly restructure the memory model, update `README.md` to match.

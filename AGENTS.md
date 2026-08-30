# LLM Instructions

These are the instructions for an LLM coding agent.

Project context:

- This is a hobby project that analyzes outdoor activity tracks.
- This project is a Flask application that uses SQLAlchemy for persistence.
- Documentation is done with Markdown and VitePress.

## Coding

Rule: Use modern Python syntax with type annotations.

Rule: Use `_(…)` for user facing strings.

Rule: If similar functionality already exist, please asks me to generalize it before creating duplicated code.
Reason: Duplicated code has a cognitive burden.

## Documentation

Rule: Don't hard-wrap Markdown content.
Reason: Editors have soft-wrap that is more flexible.

## Git

Rule: Work on `main` in this particular project.

## Communication

Rule: Only post updates to the GitHub tickets when I tell you to.

Rule: When posting content to GitHub using the `gh` CLI, be aware of newlines.
Reason: When one isn't careful, literal `\n` end up in the GitHub text.

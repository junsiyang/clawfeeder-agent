# CLAUDE.md

Project-specific guidance for Claude Code.

## Git Commit Standards

- **No Co-Authored-By** in commit messages
- **Message format**: `type: brief description` (English only)
  - `fix: handle non-JSON responses`
  - `feat: add cancel button to note modal`
  - `docs: add README`
- **Types**: `fix`, `feat`, `docs`, `chore`, `refactor`, `test`
- **Keep it short**: first line under 72 characters

## Build

**Prerequisites:** Install PyInstaller before building:
```bash
source .venv/bin/activate
pip install -r requirements.build.txt
```

**Build binary:**
```bash
bash build.sh
# Output: dist/clawfeeder-agent
```

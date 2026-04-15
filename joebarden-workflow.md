---
description: "JoeBarden Bot Development Workflow - Orchestrates agents for assessing and writing code in the JoeBarden directories"
---

# JoeBarden Development Workflow

## Quick Start
Use this workflow to assess and modify code in the JoeBarden Discord bot project.

## Directory Structure
```
workflows/github/JoeBarden/
├── JoeBardenBot3.py              # Main production bot
├── JoeBardenBeta/                # Development/Beta versions
│   ├── JoeBardenBot_Beta.py      # Current beta
│   └── JoeBardenBot_Beta_OLD.py  # Previous beta
├── requirements.txt              # Python dependencies
├── patchnotes.txt                # Changelog
└── test_*.py                     # Test scripts
```

## Invoking Agents for JoeBarden

### 1. Full Assessment + Implementation
Invoke Orchestrator with the JoeBarden Specialist:

```
Task: Assess and fix [specific issue] in JoeBarden bot
Target: workflows/github/JoeBarden/JoeBardenBeta/JoeBardenBot_Beta.py
Context: Discord music bot with AI integration, discord.py 2.x
```

The Orchestrator will:
- Route to **JoeBarden Specialist** for project-specific context
- Route to **Research Intelligence** for discord.py/yt-dlp/AI API guidance
- Route to **Code Developer** for implementation
- Route to **Code Reviewer** for correctness validation
- Route to **Code Security Reviewer** for security checks
- Route to **Code Quality Reviewer** for maintainability review

### 2. Direct Subagent Invocation (for specific tasks)

**For code changes:**
```
Delegate to Code Developer:
"Implement [feature/fix] in JoeBarden bot at workflows/github/JoeBarden/...
Follow existing patterns in JoeBardenBot3.py for audio effects.
"
```

**For JoeBarden-specific guidance:**
```
Delegate to JoeBarden Specialist:
"Analyze the current queue system in JoeBardenBot_Beta.py and recommend
improvements for handling concurrent voice channel joins."
```

**For security review of bot code:**
```
Delegate to Code Security Reviewer:
"Review Discord bot token handling, Gemini API key management,
and FFmpeg command injection risks in JoeBarden codebase."
```

## Agent Routing Reference

| Task Type | Primary Agent | Secondary Agents |
|-----------|---------------|------------------|
| Feature implementation | Code Developer | JoeBarden Specialist |
| Bug fixes | Code Developer | Code Reviewer |
| Discord.py questions | JoeBarden Specialist | Research Intelligence |
| Audio/FFmpeg issues | JoeBarden Specialist | Research Intelligence |
| AI integration issues | JoeBarden Specialist | Research Intelligence |
| Security review | Code Security Reviewer | - |
| Code quality review | Code Quality Reviewer | Code Quality Auditor |
| Platform-specific (Windows) | Windows Systems Specialist | Research Intelligence |
| Platform-specific (macOS) | Apple Systems Specialist | Research Intelligence |

## Common Tasks

### Add New Audio Effect
1. Orchestrator → JoeBarden Specialist (analyze existing effects)
2. JoeBarden Specialist → Code Developer (implement)
3. Code Developer → Code Reviewer (validate)

### Fix Discord API Issue
1. Orchestrator → Research Intelligence (check discord.py docs)
2. Research Intelligence → JoeBarden Specialist (contextualize)
3. JoeBarden Specialist → Code Developer (implement fix)

### Update AI Integration
1. Orchestrator → Research Intelligence (Gemini API changes)
2. Research Intelligence → JoeBarden Specialist (integration patterns)
3. JoeBarden Specialist → Code Developer → Code Security Reviewer

## Schema Reminders
All subagents must return their specific SCHEMA_VERSION:
- Code Reviewer: `CR-1`
- Code Security Reviewer: `CSR-1`
- Code Quality Reviewer: `CQR-1`
- Code Quality Auditor: `CQA-1`
- Research Intelligence: `RI-1`
- JoeBarden Specialist: `JBS-1`
- Windows Systems Specialist: `WSS-1`
- Apple Systems Specialist: `ASS-1`

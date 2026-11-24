# Project Context

## Project Summary
- **Project Name**: 資管科智慧學習歷程系統 (Smart Learning Portfolio System for Information Management Department)
- **Goal**: Assist students in building and managing their learning portfolios, work samples, attachments, external links, and academic transcripts, while enabling teachers and review committee members to evaluate, score, comment on, and lock portfolio reviews. Incorporates AI Agent extensions (transcript OCR/extraction drafts, evidence checking reports) as a secondary enhancement layer.
- **Primary Tech Stack**: Python (Flask 3.x), MySQL / MariaDB (SQLAlchemy), HTML5, CSS3, JavaScript, Jinja2 Templates, Gemini API / LLM Service layer.

---

## Architectural Principles & Rules
1. **Core-First Architecture**: Core business workflows (auth, CRUD, portfolio management, scoring) MUST work fully without relying on AI services.
2. **Draft & Human-in-the-Loop Pattern for AI**: AI model outputs must never write directly into official production database tables. They must land in draft/staging tables (`transcript_drafts`, `ai_audit_reports`) and require explicit user/teacher confirmation.
3. **Strict Scoped Access Control**:
   - `Student`: Can only access, view, and edit their own portfolios and data.
   - `Teacher / Evaluator`: Can only view assigned student portfolios and record review scores/comments.
   - `Admin`: Full access to user management, roles, system parameters, logs, and AI task statuses.
4. **Service Layer Isolation**: AI capabilities must be encapsulated inside `app/services/` (`agent_service.py`, `transcript_service.py`) and exposed cleanly to controllers, keeping route handlers decoupled from LLM API implementations.

---

## Workspace Structure & Key Paths
- Project Root: `d:/democase/ai`
- Core Documentation: [`docs/`](file:///d:/democase/ai/docs)
  - System Specification (Detailed): [`docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md`](file:///d:/democase/ai/docs/資管科智慧學習歷程系統-系統規格設計書-開發閱讀版.md)
  - System Diagrams: [`docs/diagrams.md`](file:///d:/democase/ai/docs/diagrams.md)
  - Database Setup: [`docs/mysql-setup.md`](file:///d:/democase/ai/docs/mysql-setup.md)
  - Development Log: [`docs/development-log.md`](file:///d:/democase/ai/docs/development-log.md)
- Codebase Directory: [`app/`](file:///d:/democase/ai/app)
- BMAD Configuration: [`_bmad/config.toml`](file:///d:/democase/ai/_bmad/config.toml)

---

## Active Development Roadmap
- **Sprint 0**: Project setup & infrastructure (Flask skeleton, virtualenv, dependencies, log structure).
- **Sprint 1**: Core authentication & RBAC (`users`, `roles`, login/logout, route protection).
- **Sprint 2**: Student portfolio CRUD (portfolio entries, file upload, external links).
- **Sprint 3**: Review & scoring workflows (review projects, assignment, scoring, status locking).
- **Sprint 4**: Admin panel & system maintenance (user management, announcements, logs, AI task status).
- **Sprint 5**: AI Transcript Extraction (OCR upload -> draft creation -> student review -> database save).
- **Sprint 6**: AI Evidence Audit (claim verification, evidence matrix, review reports).

---

## Key Domain Models
- **Implemented:**
  - `User`, `StudentProfile`
  - `Portfolio`, `PortfolioEvidence`
  - `AgentTask`, `AuditLog`
- **Roadmap Models (Planned):**
  - `Role`
  - `ReviewProject`, `ProjectAssignment`, `ReviewLog`
  - `TranscriptDraft`, `TranscriptItem`
  - `AiAuditReport`
  - `SystemLog`, `SystemSetting`

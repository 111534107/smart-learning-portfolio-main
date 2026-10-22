# 二技入學資格查詢 Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a student ask which published two-year tech-college admission programs they may apply to, with deterministic qualification results and traceable official sources.

**Architecture:** Reuse `AdmissionProgram`, confirmed student records, the existing Uni-assistant tool-calling flow, and its candidate-to-published review lifecycle. Add structured per-program eligibility rules and a deterministic matching service; the language model only explains service results. First release supports two-year technical excellence admission and information-management-related programs.

**Tech Stack:** Python, Flask, SQLAlchemy, Alembic, existing Gemini function-call assistant, pytest project conventions.

**Spec:** `docs/superpowers/specs/2026-10-22-two-year-admission-qualification-agent-design.md`

## Global Constraints

- Use the current year's official admission handbook as the rule source; historical data is reference only.
- AI-extracted rules remain pending until an administrator verifies them against the official source.
- Only confirmed student records and published program rules can produce a definite match.
- The matching service, not the language model, determines qualification status.
- Never present a result as an official decision or an admission probability.
- Reuse existing program, credential, portfolio, and profile records; do not duplicate them.
- Do not run a database migration against the user's MySQL database without a backup and explicit approval.

## Review Focus

- A rule with an alternative condition group must not accidentally require every alternative; keep AND-within-group and OR-between-groups explicit.
- A pending rule must never result in a definite “符合目前已知條件” result.
- Unconfirmed OCR records, missing admission year, and unsupported comparison fields must result in “資料不足／需人工確認”.
- A rule must not match records from another student, even if the assistant tool call supplies a student identifier.
- Missing official source details must be visible and must not be represented as verified evidence.

---

### Task 1: Add the structured eligibility-rule model and migration

**Files:**
- Modify: `app/models/admission.py`
- Modify: `app/models/__init__.py`
- Create: next Alembic migration under `migrations/versions/`
- Modify: `tests/test_migration_setup.py`

**Interfaces:**
- Produces `AdmissionEligibilityRule`, related to one `AdmissionProgram` through `rule_version_id`.
- Fields: `rule_group` (integer), `condition_type` (string), `operator` (string), `value_json` (JSON), `description` (text), `source_url` (string), `source_location` (string), `mapping_status` (`pending`/`confirmed`), `is_required` (boolean), and `sort_order` (integer).
- Group semantics: all required rules within one group are ANDed; a program matches if at least one complete group matches (OR between groups). Nonrequired rules are informational and do not block a match.

- [ ] Add the SQLAlchemy model and `AdmissionProgram.eligibility_rules` relationship; export the model from `app.models`.
- [ ] Add a reversible migration creating `admission_eligibility_rules`, its program foreign key, and a lookup index on `rule_version_id` and `mapping_status`.
- [ ] Ensure the existing SQLite migration-upgrade/downgrade workflow includes and removes the new table without removing earlier admission tables.

### Task 2: Implement deterministic eligibility evaluation

**Files:**
- Create: `app/services/admission_eligibility_service.py`
- Modify: `app/services/journey_service.py` only if a reusable grade derivation interface is required
- Create: `tests/test_admission_eligibility_service.py`

**Interfaces:**
- `evaluate_program(student, program) -> dict` returns `program_code`, `admission_year`, `status`, `matched_groups`, `conditions`, and `sources`.
- Supported first-release condition types: `student_status`, `credential`, and `competition`.
- Supported operators and the exact JSON value shapes must be defined as module-level validators before matching: `student_status` accepts an allowed status list; `credential` accepts optional normalized name, minimum level, issuer, and issue-date bounds; `competition` accepts optional category, award/rank threshold, and date bounds.
- Any unknown condition type/operator, invalid value shape, pending mapping, or unavailable student field yields `needs_review`/`insufficient_data`; it cannot count as a match.
- Student credential evaluation reads only `CredentialRecord` rows with `confirmation_status == "confirmed"`; competition evaluation reads only the logged-in student's `Portfolio` rows with `status == "confirmed"`.
- Certificate level normalization uses an explicit ordered mapping; unknown certificate names or level labels are unresolved, not guessed.

- [ ] Define and validate the supported `value_json` shapes and comparison operators.
- [ ] Implement group evaluation with AND within each group and OR across groups; return per-condition explanations rather than only a boolean.
- [ ] Return `eligible`, `not_eligible`, `insufficient_data`, or `needs_review` using the precedence rules in the design spec; include each applicable source URL and location.
- [ ] Keep unknown certificate levels, competition rank/category, or unsupported data fields unresolved instead of inferring a match from free text.

### Task 3: Extract eligibility candidates from official source snapshots

**Files:**
- Modify: `app/services/admission_agent_service.py`
- Modify: `tests/test_admission_agent.py`

**Interfaces:**
- Extend the extraction schema with an `eligibility_rules` array. Each candidate contains `rule_group`, `condition_type`, `operator`, `value_json`, `description`, and `source_location`.
- `extract_programs(...)` stores extracted eligibility rules as `mapping_status="pending"` and links them to the exact program version and source URL.
- Existing score-item extraction behavior remains intact.

- [ ] Update the prompt/schema to extract only explicit eligibility language and page/section location from the source snapshot.
- [ ] Persist valid extracted rules as pending; reject malformed rule shapes and preserve the source description for admin review.
- [ ] Ensure a missing, illegible, or ambiguous requirement creates no guessed structured condition; retain an unresolved candidate note for review.

### Task 4: Add administrator review for eligibility rules

**Files:**
- Modify: `app/routes/admin.py`
- Modify: `app/templates/admin_programs.html` (or the admission review template used by the current routes)
- Modify: `tests/test_admission_services.py`

**Interfaces:**
- Administrator actions are scoped to an existing `AdmissionProgram` candidate and its `AdmissionEligibilityRule` rows.
- Each rule can be corrected and marked `confirmed`, or left pending; publication continues to use the existing program status workflow.
- The review view shows description, normalized condition, source link, source location, and mapping status together.

- [ ] Add an admin-only rule-review action that validates edits against the condition schema before saving.
- [ ] Show pending rules alongside their official source details in the existing admission review experience.
- [ ] Prevent a program from being represented as qualification-verified when its required eligibility rules are still pending; keep unstructured rules visible with a “需人工確認” state.

### Task 5: Expose qualification lookup as a student assistant tool

**Files:**
- Modify: `app/services/assistant_tools.py`
- Modify: `app/services/assistant_service.py`
- Modify: `tests/test_assistant.py`

**Interfaces:**
- Add student tool `find_eligible_admission_programs(user, admission_year=None) -> dict`; derive the student identity from `user`, never from model-supplied identity arguments.
- The tool queries only published programs for the requested year (or the latest explicitly available year) and returns each result from `evaluate_program` plus program name and official source references.
- Register the tool only for the student role in `STUDENT_TOOLS`; teacher lookup is out of this first release.
- Assistant system instruction explains status labels and requires it to distinguish rule-engine results from official admission review.

- [ ] Implement and register the student-only lookup tool, limiting results to the current student's confirmed profile records.
- [ ] Update the assistant instruction to call the tool for questions about personal two-year/technical-excellence eligibility and to explain each status without inventing requirements.
- [ ] Return source links and page/section locations in the existing assistant `sources` response format where possible; include structured source details in the tool result for the final answer.

### Task 6: Complete migration, permission, and end-to-end review

**Files:**
- Modify: `tests/test_migration_setup.py`
- Modify: `tests/test_admission_eligibility_service.py`
- Modify: `tests/test_assistant.py`
- Modify: `docs/02_需求與設計/01_目前有效/AI_資料字典_現行ORM草稿_2026-10-13.md`

- [ ] Verify an eligible student gets an explanation tied to the matching source rule and an ineligible student gets the failed condition.
- [ ] Verify alternative groups, pending rules, OCR-unconfirmed credentials, unconfirmed competition portfolios, missing profile fields, unsupported competition details, and year filtering produce the expected non-overstated status.
- [ ] Verify assistant tool access uses the authenticated student and cannot query another student's records.
- [ ] Verify the migration can upgrade and downgrade a disposable SQLite database; do not run it on MySQL as part of this plan.
- [ ] Update the current ORM data dictionary with the eligibility-rule table and its review/source fields.


# School Google Login Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let pre-registered students sign in with a verified `@stu.ukn.edu.tw` Google Workspace account.

**Architecture:** Add a dedicated server-side OpenID Connect callback and a stable Google subject binding on users. Admins bind a unique school email to an existing student; the callback verifies the identity before using the existing student login flow.

**Tech Stack:** Flask, SQLAlchemy, Alembic, Google auth Python library, pytest.

**Spec:** `docs/superpowers/specs/2026-11-02-school-google-login.md`

## Global Constraints

- School domain: `stu.ukn.edu.tw` exactly.
- Student accounts must already exist; Google login must not create them.
- Preserve password login and existing student data.

## Review Focus

- Unverified email and absent or wrong `hd` must fail.
- Unbound, duplicate, inactive or nonstudent accounts must fail.
- State mismatch or replay must fail before exchanging the code.
- Changed Google email for an existing sub must fail until an admin rebinds it.
- A missing OAuth configuration must hide the button and not contact Google.

---

### Task 1: Google identity and callback

- [x] Write callback tests for successful login and each rejection above.
- [x] Run them and confirm the expected failures.
- [x] Add Google token verification, dedicated OAuth routes and the login button.
- [x] Run callback tests until green.

### Task 2: Admin binding and deployment

- [x] Write tests for admin binding, validation and duplicate rejection.
- [x] Run them and confirm the expected failures.
- [x] Add model field, migration, admin form and configuration documentation.
- [x] Run relevant tests and check the migration and final diff.

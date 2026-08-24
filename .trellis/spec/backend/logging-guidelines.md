# Logging Guidelines

> How logging is done in this project.

---

## Overview

<!--
Document your project's logging conventions here.

Questions to answer:
- What logging library do you use?
- What are the log levels and when to use each?
- What should be logged?
- What should NOT be logged (PII, secrets)?
-->

The backend uses Python logging with `python-json-logger`. Application logging is
configured once by the app factory and emits JSON records.

---

## Log Levels

<!-- When to use each level: debug, info, warn, error -->

Use INFO for lifecycle/request/job completion, WARNING for degraded dependencies,
and ERROR/exception for unexpected failures. Health probes should not create
unbounded high-volume logs.

---

## Structured Logging

<!-- Log format, required fields -->

Request records include operation/path, result status, duration, and correlation
ID. Worker diagnostics include the job operation and correlation context.
`RedactingFormatter` recursively masks secret-like keys.

---

## What to Log

<!-- Important events to log -->

Log request completion, migration/worker lifecycle failures, retry outcomes, and
readiness degradation with low-cardinality fields.

---

## What NOT to Log

<!-- Sensitive data, PII, secrets -->

Never log passwords, tokens, API keys, authorization headers, private keys,
connection strings, request bodies, or document content. Redaction is based on
secret-like field names and must remain recursive.

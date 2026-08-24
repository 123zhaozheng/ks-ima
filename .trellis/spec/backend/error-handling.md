# Error Handling

> How errors are handled in this project.

---

## Overview

<!--
Document your project's error handling conventions here.

Questions to answer:
- What error types do you define?
- How are errors propagated?
- How are errors logged?
- How are errors returned to clients?
-->

HTTP errors are normalized as RFC 9457 Problem Details. Internal exception text,
settings, connection strings, and secrets are never returned to clients.

---

## Error Types

<!-- Custom error classes/types -->

`ProblemDetails` is the public contract. Stable `code` values identify errors;
`correlationId` is returned in both the body and `X-Correlation-ID` header.

---

## Error Handling Patterns

<!-- Try-catch patterns, error propagation -->

Map Starlette HTTP and validation exceptions centrally. Log unexpected failures
with correlation context and return a generic `INTERNAL_ERROR` response.

---

## API Error Responses

<!-- Standard error response format -->

Use media type `application/problem+json` with `type`, `title`, `status`,
`detail`, `instance`, `code`, `correlationId`, and optional field errors.

---

## Common Mistakes

<!-- Error handling mistakes your team has made -->

Do not expose Pydantic raw validation payloads, database errors, stack traces, or
secret-bearing URLs. Add contract tests for every new public error shape.

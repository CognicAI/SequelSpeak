# URL Parsing Bug Report

## Issue Description
When a PostgreSQL connection string contains square brackets `[` or `]` in the password field, the `urllib.parse.urlparse` function in Python fails to parse the URL correctly, raising a `ValueError`.

## Error Message
```
ValueError: 'aws-1-ap-southeast-1.pooler.supabase.com' does not appear to be an IPv4 or IPv6 address
```
(Note: The specific hostname in the error message depends on the URL provided)

## Reproduction
An example URL that triggers this issue:
```
postgresql://postgres.user:[password_with_brackets]@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres
```

## Root Cause
The `urllib.parse` library treats square brackets as delimiters for IPv6 address literals (e.g., `[::1]`). When found in the user info section (password), it misinterprets the structure of the URL, leading to incorrect parsing logic that attempts to validate the hostname as an IP address under the assumption that an IPv6 literal was involved or malformed.

## Workaround
To use special characters like brackets in the password, they must be URL-encoded:
- `[` should be `%5B`
- `]` should be `%5D`

Example:
`...:pass%5Bword%5D@...` instead of `...:pass[word]@...`

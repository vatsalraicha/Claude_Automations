# Connector notes — Jira

Filled in during SETUP. Later iterations read this file instead of re-discovering how the connector works.
Never write credentials or tokens in this file.

## Read operations used by this loop

### Read one ticket by key
```
```
Fields returned:
- summary / type / status / resolution / created / updated:
- description:
- acceptance criteria (which field holds it here):
- parent / epic:
- issue links:
- comments:

### List project keys
```
```

## Never call
(every write operation the connector offers: create, edit, transition, comment, assign, link, ...)
- 

## Limits and quirks
- Rate limit:
- 

# Integration test: SupabaseStore against real PostgREST

Skipped by default. It needs Docker and a throwaway database — never point it at a real project.

```bash
tests/integration/run.sh        # starts Postgres+pgvector and PostgREST, runs the test, tears down
```

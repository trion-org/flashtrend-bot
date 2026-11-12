-- Migration 19 — the Kaggle quota ledger of each account lives in Supabase, not in a file on each machine.
-- Safe to run again. Additive: one nullable column on gpu_accounts.
--
-- estfstudio used to keep, per Kaggle account, the GPU sessions it ran, Kaggle's own last count of the weekly hours
-- (`live`), and why/until when the account is skipped, in ~/.config/estfstudio/kaggle_quota.json — so every machine
-- worked from its own picture of a quota that is really shared. Now the whole entry is this column and every machine
-- reads and writes it here (hours_left / used_up_* stay as the readable summary).
-- TEXT AND NUMBERS ONLY: session start/end times, hour counts, reasons — never a key or a token.

alter table gpu_accounts add column if not exists ledger jsonb;

notify pgrst, 'reload schema';

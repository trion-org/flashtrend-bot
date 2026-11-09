-- Migration 14 — drop the Shopee comment templates and product ideas of migrations 12 and 13.
-- estfstudio no longer has /comment or /keywords: the admin gives the affiliate links among the questions of /posts,
-- and the wording by occasion now lives in estfstudio's affiliate_comments.yaml (the templates of migration 12 were
-- moved there as they were; the product ideas of migration 13 were not kept).
-- Safe to run again: every statement is `if exists`. Order matters: product_ideas and the two children reference
-- comment_occasions.

drop table if exists product_ideas;
drop table if exists comment_templates;
drop table if exists comment_windows;
drop table if exists comment_occasions;

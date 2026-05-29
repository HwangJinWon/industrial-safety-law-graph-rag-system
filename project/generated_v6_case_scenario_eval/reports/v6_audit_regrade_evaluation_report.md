# v6 Audit Regrade Evaluation Report

## Dataset Split
- A1_STRICT: audit ok; strict evaluation target. Re-evaluated with selected_laws cap=8.
- A2_ARTICLE_LEVEL_AUX: article-level penalty GT; auxiliary article/fine split evaluation, kept separately.
- A3_REVIEW_ONLY: no core selected slot; excluded from strict and auxiliary evaluation until obligation review.

## Metrics
- A1_strict_cap8: n=12, selected_count=8.000, role_f1=0.470, article_f1=0.314, fine_f1=0.234, chain_exists=1.000, chain_article_f1=0.198, chain_fine_f1=0.115, candidate_overgen=1.050
- A1_A2_aux_cap10: n=23, selected_count=10.000, role_f1=0.385, article_f1=0.158, fine_f1=0.106, chain_exists=1.000, chain_article_f1=0.103, chain_fine_f1=0.060, candidate_overgen=2.099
- full_READY_A_cap10: n=40, selected_count=10.000, role_f1=0.258, article_f1=0.091, fine_f1=0.061, chain_exists=0.000, chain_article_f1=0.000, chain_fine_f1=0.000, candidate_overgen=2.407

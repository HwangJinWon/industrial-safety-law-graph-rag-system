# STEP 2 Fine Candidate Expansion Report

## Missing Types Before Expansion
Strict:
{
  "corporate_penalty_fine_missing": 17,
  "article_family_missing": 17,
  "definition_scope_fine_missing": 9,
  "article_family_hit_but_fine_missing": 3,
  "detail_rule_fine_missing": 2,
  "penalty_fine_missing": 2
}

Auxiliary:
{
  "article_family_missing": 17,
  "definition_scope_fine_missing": 1
}

## Expansion Rules Applied
Strict:
{
  "supporting_definition_article_family_hit": 9,
  "core_article_family_hit": 2,
  "supporting_enforcement_decree_detail_article_family_hit": 2
}

Auxiliary:
{
  "supporting_definition_article_family_hit": 1
}

## Before / After
Strict candidate_fine_recall:
0.629 -> 0.703

Strict candidate_fine_missing per case:
1.852 -> 1.370

Strict candidate pool size:
33.667 -> 34.148

## Note
Expanded refs are not promoted to selected. They remain candidate/supporting candidates so candidate recall and selected decision quality stay separated.

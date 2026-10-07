# $schema: ../schemas/dataset_schema.json
# Evaluation dataset for the Agentic Text-to-SQL Analytics Platform.
# Each case is a self-contained question→gold_sql pair.
#
# Fields:
#   id           – stable lowercase-slug unique ID
#   db           – "ecommerce" | "pagila"
#   question     – natural language user question
#   gold_sql     – correct SQL; may reference {as_of_date} for relative dates
#   difficulty   – "easy" | "medium" | "hard"
#   category     – "aggregation" | "join" | "filter" | "time" | "grouping" |
#                  "subquery" | "schema_question" | "followup" | "ambiguous" |
#                  "unsupported" | "adversarial"
#   expected_intent – "ANSWER" | "CLARIFICATION_REQUIRED" | "UNSUPPORTED_REQUEST" |
#                     "SCHEMA_QUESTION"
#   expected_tables  – list of schema-qualified table names the gold SQL touches
#   order_sensitive  – true only when gold_sql has a meaningful ORDER BY
#   followup_of      – id of the parent question (for follow-up chains), else null
#   notes            – optional explanation or known limitation
#   split            – "dev" | "test"  (assigned deterministically; do not change)

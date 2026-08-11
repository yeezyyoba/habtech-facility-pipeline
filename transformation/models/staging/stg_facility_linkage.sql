select
  mfr_id,
  dhis2_uid as llm_dhis2_uid,
  confidence as llm_confidence,
  reason as llm_reason
from {{ source('raw', 'facility_linkage') }}

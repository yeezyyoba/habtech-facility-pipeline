{{ config(materialized='table', engine='MergeTree', order_by='mfr_id') }}
select
  m.mfr_id,
  m.facility_name,
  m.facility_type,
  m.ownership,
  m.region,
  m.zone,
  m.woreda,
  m.catchment_population,
  m.number_of_inpatient_beds,
  m.number_of_maternity_beds,
  m.number_of_emergency_beds,
  m.number_of_opd_rooms,
  m.number_of_ipd_rooms,
  m.number_of_laboratory_rooms,
  m.number_of_imaging_rooms,
  m.number_of_mch_rooms,
  m.number_of_icu_rooms,
  coalesce(nullif(m.existing_dhis2_id, ''), l.llm_dhis2_uid) as dhis2_uid,
  case
    when m.existing_dhis2_id is not null and m.existing_dhis2_id != '' then 'linked_original'
    when l.llm_dhis2_uid is not null then 'linked_llm'
    else 'unlinked'
  end as linkage_status,
  l.llm_confidence,
  l.llm_reason
from {{ ref('stg_mfr_facilities') }} m
left join {{ ref('stg_facility_linkage') }} l on m.mfr_id = l.mfr_id

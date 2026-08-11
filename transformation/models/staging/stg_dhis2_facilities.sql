select
  uid as dhis2_uid,
  name as dhis2_name,
  regional,
  zonal,
  wereda,
  facilitytype,
  ownership as dhis2_ownership,
  level
from {{ source('raw', 'dhis2_facilities') }}

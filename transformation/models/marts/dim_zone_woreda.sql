{{ config(materialized='table', engine='MergeTree', order_by='(region, zone, woreda)', settings={'allow_nullable_key': 1}) }}
select distinct region, zone, woreda
from {{ ref('stg_mfr_facilities') }}
where zone is not null

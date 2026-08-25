{{ config(materialized='table', engine='MergeTree', order_by='region', settings={'allow_nullable_key': 1}) }}
select distinct region
from {{ ref('stg_mfr_facilities') }}
where region is not null

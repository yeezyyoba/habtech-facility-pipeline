{{ config(materialized='table', engine='MergeTree', order_by='region') }}
select distinct region
from {{ ref('stg_mfr_facilities') }}
where region is not null

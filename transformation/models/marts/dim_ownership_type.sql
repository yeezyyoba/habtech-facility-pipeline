{{ config(materialized='table', engine='MergeTree', order_by='ownership') }}
select distinct ownership
from {{ ref('stg_mfr_facilities') }}
where ownership is not null

{{ config(materialized='table', engine='MergeTree', order_by='ownership', settings={'allow_nullable_key': 1}) }}
select distinct ownership
from {{ ref('stg_mfr_facilities') }}
where ownership is not null

{#
    By default dbt builds custom schemas as <target_schema>_<custom_schema>
    (e.g. STAGING_MARTS). Override it so `+schema: MARTS` means exactly MARTS.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim | upper }}
    {%- endif -%}
{%- endmacro %}

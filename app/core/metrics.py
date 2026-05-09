"""Central Prometheus metrics registry.

All metrics are defined here so they are imported as singletons — defining
the same metric name twice in different modules raises a ValueError at import
time, which would break startup.  Import individual counters/histograms from
this module wherever you need to record an observation.

Label cardinality is intentionally limited: ngo_slug (not ngo_id) keeps
the label set bounded as NGO count grows; agent_name is an enum-like set of
five values, so combinatorial explosion is not a concern.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Product / business metrics
# ---------------------------------------------------------------------------

messages_processed = Counter(
    "ngoopsbot_messages_processed_total",
    "Total Telegram messages processed by the platform",
    ["ngo_slug", "agent_name", "message_type"],  # message_type: text/voice/document
)

agent_invocations = Counter(
    "ngoopsbot_agent_invocations_total",
    "Total times an agent was invoked (one per user turn routed to an agent)",
    ["ngo_slug", "agent_name"],
)

tokens_consumed = Counter(
    "ngoopsbot_tokens_consumed_total",
    "Cumulative LLM tokens consumed (input + output combined)",
    ["ngo_slug", "agent_name"],
)

reminders_sent = Counter(
    "ngoopsbot_reminders_sent_total",
    "Total reminders dispatched to any delivery channel",
    ["ngo_slug", "channel"],  # channel: telegram / sms / email
)

whisper_transcriptions = Counter(
    "ngoopsbot_whisper_transcriptions_total",
    "Voice messages sent to Whisper for transcription",
    ["ngo_slug", "status"],  # status: success / error
)

google_api_calls = Counter(
    "ngoopsbot_google_api_calls_total",
    "Calls made to Google APIs on behalf of NGOs",
    ["ngo_slug", "service"],  # service: drive / sheets
)

# ---------------------------------------------------------------------------
# System / operational metrics
# ---------------------------------------------------------------------------

active_ngos = Gauge(
    "ngoopsbot_active_ngos",
    "Number of NGO tenants with is_active=True",
)

agent_response_latency = Histogram(
    "ngoopsbot_agent_response_latency_seconds",
    "End-to-end latency for a complete agent turn (first token to final response)",
    ["ngo_slug", "agent_name"],
    # Buckets tuned for conversational UX: <2 s is great, >30 s is a timeout risk
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

db_query_latency = Histogram(
    "ngoopsbot_db_query_latency_seconds",
    "Latency for individual database queries (instrumented in service layer)",
    [],
    buckets=[0.01, 0.05, 0.1, 0.5, 1],
)

external_api_latency = Histogram(
    "ngoopsbot_external_api_latency_seconds",
    "HTTP call latency to third-party APIs",
    ["service"],  # service: anthropic / openai / sendgrid / msg91 / telegram
)

# ---------------------------------------------------------------------------
# Cache metrics
# ---------------------------------------------------------------------------

cache_hits = Counter(
    "ngoopsbot_cache_hits_total",
    "Redis cache hits, labelled by key prefix for per-feature drill-down",
    ["key_prefix"],
)

cache_misses = Counter(
    "ngoopsbot_cache_misses_total",
    "Redis cache misses, labelled by key prefix",
    ["key_prefix"],
)

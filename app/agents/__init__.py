# Import all agent modules so their @register_agent decorators fire at startup.
from app.agents import fundraising, finance, marketing, hr, compliance  # noqa: F401

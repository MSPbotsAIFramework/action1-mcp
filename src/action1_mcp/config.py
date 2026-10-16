# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Process settings. Holds no credentials: those arrive per request as headers."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Action1 data centres (canonical name -> API base URL).
REGION_BASE_URLS: dict[str, str] = {
    "NorthAmerica": "https://app.action1.com/api/3.0",
    "NorthAmerica-2": "https://app.na-2.action1.com/api/3.0",
    "Europe": "https://app.eu.action1.com/api/3.0",
    "UnitedKingdom": "https://app.uk.action1.com/api/3.0",
    "Australia": "https://app.au.action1.com/api/3.0",
}
DEFAULT_REGION = "NorthAmerica"

# Accepted spellings (case-insensitive) -> canonical region name.
REGION_ALIASES: dict[str, str] = {
    **{name.lower(): name for name in REGION_BASE_URLS},
    "na": "NorthAmerica",
    "us": "NorthAmerica",
    "na-2": "NorthAmerica-2",
    "na2": "NorthAmerica-2",
    "eu": "Europe",
    "uk": "UnitedKingdom",
    "au": "Australia",
}


def resolve_region(value: str | None) -> str | None:
    """Canonical region for a header value; DEFAULT_REGION when blank, None when unknown."""
    text = (value or "").strip()
    if not text:
        return DEFAULT_REGION
    return REGION_ALIASES.get(text.lower())


class Settings(BaseSettings):
    # extra="ignore": the runtime injects variables this project does not declare.
    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_port: int = 8080
    mcp_http_host: str = "0.0.0.0"
    log_level: str = "INFO"


def get_settings() -> Settings:
    return Settings()

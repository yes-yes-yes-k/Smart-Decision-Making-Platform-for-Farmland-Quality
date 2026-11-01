"""Shared extraction identity and explicitly allowed model destinations."""
import os
from urllib.parse import urlsplit
from .contracts import stable_digest


def model_endpoint():
    value = os.environ.get("KG_EXTRACTION_BASE_URL", "http://127.0.0.1:8001/v1")
    parsed = urlsplit(value)
    local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    siliconflow = (os.environ.get("KG_EXTRACTION_ALLOW_SILICONFLOW") == "true" and
                   value.rstrip("/") == "https://api.siliconflow.cn/v1")
    if (parsed.scheme not in {"http", "https"} or not (local or siliconflow) or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("extraction_endpoint_must_be_local_or_authorized_siliconflow")
    return value


def backend_config_digest(backend_name, extractor_version, schema_version):
    config = dict(backend_name=backend_name, extractor_version=extractor_version,
                  schema_version=schema_version)
    if backend_name == "microsoft-graphrag":
        config.update(model=os.environ.get("KG_EXTRACTION_MODEL", ""),
                      endpoint=os.environ.get("KG_EXTRACTION_BASE_URL", "http://127.0.0.1:8001/v1"),
                      prompt_version=("typed-relations-v7-literal-evidence-repair2"
                          if os.environ.get('KG_EXTRACTION_LITERAL_EVIDENCE') == 'true'
                          else "typed-relations-v6-json-schema-repair2"),
                      max_tokens=os.environ.get("KG_EXTRACTION_MAX_TOKENS", "4096"))
    return stable_digest(config)

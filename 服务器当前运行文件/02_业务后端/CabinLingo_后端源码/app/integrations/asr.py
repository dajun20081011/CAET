from .ai_gateway import AudioLoader
from .http_ai_adapter import HTTPAIAdapter, ProviderConfig
from .http_client import HTTPClient
from .result_parser import parse_asr


class ASRIATAdapter(HTTPAIAdapter):
    def __init__(self, config: ProviderConfig, audio_loader: AudioLoader, client: HTTPClient | None = None) -> None:
        super().__init__(config, parse_asr, audio_loader, client)

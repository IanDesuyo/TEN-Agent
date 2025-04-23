from .log import logger
from .prompts import DEFAULT_TRANSLATE_USER_PROMPT

ENGINES = ["vllm"]
MODELS = ["llama"]

class SageMakerLLMConfig:
    def __init__(self):
        self.region = "us-east-1"
        self.access_key = ""
        self.secret_key = ""
        self.endpoint_name = ""
        self.engine = "vllm"
        self.model = "llama"
        self.max_tokens = 1024
        self.temperature = 0.7
        self.top_p = 1.0
        self.prompt = ""
        self.mode = "chat"
        self.input_language = ""
        self.output_language = ""
        self.chat_template = ""

    @classmethod
    def default_config(cls):
        return cls()

    def validate(self):
        self.engine = self.engine.lower()

        if not self.engine in ENGINES:
            raise ValueError("Engine [{self.engine}] not valid, must in [{ENGINES}]")

        if not self.model in MODELS:
            raise ValueError("Engine [{self.model}] not valid, must in [{MODELS}]")

        if self.mode == 'translate':
            if not self.input_language or not self.output_language:
                err_msg = "input_language and output_language must be set when mode is 'translate'"
                logger.error(err_msg)
                raise ValueError(err_msg)

            if not self.chat_template.strip():
                logger.warning("chat_template is not set, using default value")
                self.chat_template = DEFAULT_TRANSLATE_USER_PROMPT

            # logger.info(self.chat_template)
            self.chat_template = self.chat_template.format(
                input_language=self.input_language,
                output_language=self.output_language
            )
        elif self.mode == 'chat':
            if self.chat_template.strip():
                logger.warning("chat_template is set, but mode is 'chat', ignoring chat_template")
                self.chat_template = ''
        else:
            logger.error(f"unknown mode: {self.mode}, fallback to 'chat'")
            self.mode = 'chat'

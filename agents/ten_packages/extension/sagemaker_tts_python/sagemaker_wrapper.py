import io
import json
from dataclasses import dataclass
from typing import Union

import boto3
from botocore.exceptions import ClientError
from ten_ai_base.config import BaseConfig

from .log import logger

MODEL_TYPE_GPT_SOVITS = "gpt_sovits"
MODEL_TYPE_XTTS = "xtts"

MODEL_TYPES = [
    MODEL_TYPE_GPT_SOVITS,
    MODEL_TYPE_XTTS,
]

LANGCODE_MAP = {
    MODEL_TYPE_GPT_SOVITS: {
        "zh-CN": "zh",
        "en-US": "en",
        "ja-JP": "ja",
        "fr-FR": "fr",
        "ko-KR": "ko",
    },
    MODEL_TYPE_XTTS: {
        # https://huggingface.co/coqui/XTTS-v2
        # English (en), Spanish (es), French (fr), German (de), Italian (it),
        # Portuguese (pt), Polish (pl), Turkish (tr), Russian (ru),
        # Dutch (nl), Czech (cs), Arabic (ar), Chinese (zh-cn),
        # Japanese (ja), Hungarian (hu), Korean (ko) Hindi (hi).
        "zh-CN": "zh-cn",
        "en-US": "en",
        "ja-JP": "ja",
        "fr-FR": "fr",
        "ko-KR": "ko",
    },
}

LANGCODE_DEFUALT = {MODEL_TYPE_GPT_SOVITS: "en", MODEL_TYPE_XTTS: "en"}


@dataclass
class SageMakerTTSConfig(BaseConfig):
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = ""
    endpoint: str = ""
    sample_rate: int = 16000
    prompt_audio: str = ""
    prompt_text: str = ""
    prompt_language: str = ""
    output_language: str = "en"
    model_type: str = "gpt_sovits"


class SageMakerTTSWrapper:
    """Encapsulates Amazon SageMaker functions."""

    def __init__(self, config: SageMakerTTSConfig):
        """
        :param config: A SageMakerConfig
        """

        self.config = config

        if config.access_key and config.secret_key:
            logger.info(
                f"SageMakerTTS initialized with access key: {config.access_key}"
            )

            self.client = boto3.client(
                service_name="sagemaker-runtime",
                region_name=config.region,
                aws_access_key_id=config.access_key,
                aws_secret_access_key=config.secret_key,
            )
        else:
            logger.info(
                f"SageMakerTTS initialized without access key, using default credentials provider chain."
            )
            self.client = boto3.client(
                service_name="sagemaker-runtime", region_name=config.region
            )

    def get_request_payload(self, text, language):
        if self.config.model_type == MODEL_TYPE_GPT_SOVITS:
            request = {
                "refer_wav_path": self.config.prompt_audio,
                "prompt_text": self.config.prompt_text,
                "prompt_language": self.config.prompt_language,
                "text": text,
                "text_language": language,
                "output_s3uri": "",
                "cut_punc": ",.;?!、，。？！；：…",
            }
        else:
            request = {
                "speaker_wav": self.config.prompt_audio,
                "text": text,
                "language_id": language,
                # optional parameters
                "temperature": 0.75,
                "top_k": 50,
                "top_p": 0.85,
                "speed": 1,
            }

        return request

    def synthesize(self, text, language):
        """
        Synthesizes speech or speech marks from text, using the specified voice.

        :param text: The text to synthesize.
        :return: The audio stream that contains the synthesized speech and a list
                 of visemes that are associated with the speech audio.
        """
        try:
            request = self.get_request_payload(text, language)
            audio_stream = self.invoke_streams_endpoint(request)
            # audio_stream = response["AudioStream"]
            logger.info("Got audio stream.")
        except ClientError:
            logger.exception("Couldn't get audio stream.")
            raise
        else:
            return audio_stream

    def invoke_streams_endpoint(self, request):
        content_type = "application/json"
        payload = json.dumps(request, ensure_ascii=False)

        resp = self.client.invoke_endpoint_with_response_stream(
            EndpointName=self.config.endpoint,
            ContentType=content_type,
            Body=payload,
        )

        logger.info(resp["ResponseMetadata"])
        event_stream = iter(resp["Body"])

        return event_stream
        # result = []

        # for event in event_stream:
        #     chunk_bytes = event['PayloadPart']['Bytes']
        #     result.append(chunk_bytes)

        # print("All chunks processed")
        # print(f"Received {len(result)} chunks")
        # return result

    def invoke_streams_endpoint1(self, request):
        content_type = "application/json"
        payload = json.dumps(request, ensure_ascii=False)

        resp = self.client.invoke_endpoint_with_response_stream(
            EndpointName=self.config.endpoint,
            ContentType=content_type,
            Body=payload,
        )

        chunk_bytes = None
        result = []
        logger.info(resp["ResponseMetadata"])
        event_stream = iter(resp["Body"])
        index = 0
        try:
            while True:
                event = next(event_stream)
                eventChunk = event["PayloadPart"]["Bytes"]
                chunk_dict = {}
                if index == 0:
                    print("Received first chunk")
                    chunk_dict["first_chunk"] = True
                    chunk_dict["bytes"] = eventChunk
                    chunk_bytes = eventChunk
                    chunk_dict["last_chunk"] = False
                    chunk_dict["index"] = index
                else:
                    chunk_dict["first_chunk"] = False
                    chunk_dict["bytes"] = eventChunk
                    chunk_bytes = eventChunk
                    chunk_dict["last_chunk"] = False
                    chunk_dict["index"] = index
                # if index < 10:
                # print(f"[{time.time()}] chunk len:",len(chunk_dict['bytes']))
                result.append(chunk_dict)
                index += 1
                # print('返回chunk：', chunk_dict['bytes'])
        except StopIteration:
            print("All chunks processed")
            chunk_dict = {}
            chunk_dict["first_chunk"] = False
            chunk_dict["bytes"] = chunk_bytes
            chunk_dict["last_chunk"] = True
            chunk_dict["index"] = index - 1
            result = self.upsert(result, chunk_dict)
        print("result", result)
        return result

    def upsert(self, lst, new_dict):
        for i, item in enumerate(lst):
            if new_dict["index"] == i:
                lst[i] = new_dict
                return lst
        lst.append(new_dict)
        return lst

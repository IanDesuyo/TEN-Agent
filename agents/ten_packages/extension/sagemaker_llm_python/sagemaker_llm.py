import json
import boto3
from botocore.exceptions import ClientError
from typing import List, Any, Dict

from .sagemaker_llm_config import SageMakerLLMConfig
from .log import logger

class SageMakerLLM:
    """Encapsulates Amazon SageMaker functions."""

    def __init__(self, config: SageMakerLLMConfig):
        """
        :param config: A SageMakerConfig
        """

        self.config = config

        if config.access_key and config.secret_key:
            logger.info(f"SageMakerLLM initialized with access key: {config.access_key}")

            self.client = boto3.client(service_name='sagemaker-runtime', 
                                    region_name=config.region,
                                    aws_access_key_id=config.access_key,
                                    aws_secret_access_key=config.secret_key)
        else:
            logger.info(f"SageMakerLLM initialized without access key, using default credentials provider chain.")
            self.client = boto3.client(service_name='sagemaker-runtime', region_name=config.region)


    def get_stream_resp(self, messages: List[Dict[str,Any]]):
        """
        Get LLM response event stream from SageMaker Endpoint.

        :param messages (List[Dict[str,Any]]): 需要进行推理的消息列表。
            messages = [
                {"role": "system", "content":"请始终用中文回答"},
                {"role": "user", "content": "你是谁？你是干嘛的"},
            ]
        :return: Text Stream
        """
        try:
            request = {
                "model": self.config.model,
                "messages": messages,
                "stream": True,
                "max_tokens": self.config.max_tokens,
                "temperature": self.config.temperature,
                "top_p": self.config.top_p
            }

            chat_template = self.config.chat_template
            if chat_template:
                request['chat_template'] = chat_template

            llm_resp_stream = self.invoke_streams_endpoint(request)

            buffer = ''
            for event in llm_resp_stream:
                try:
                    payload = event['PayloadPart']['Bytes'].decode('utf-8')
                    if payload.endswith('\n\n'):
                        payload = buffer + payload
                        buffer = ''
                    else:
                        buffer += payload
                        continue
                    if not payload or payload.startswith('data: [DONE]'):
                        break

                    payload = payload[6:].strip()
                    if payload:
                        choices = json.loads(payload)['choices']
                        logger.info(choices[0]['delta']['content'])
                        yield choices[0]['delta']['content']
                except Exception as err:
                    logger.exception(err)

            logger.info("Got LLM Resp stream.")
        except ClientError as err:
            logger.exception(f"Couldn't get LLM Resp stream. err: {err}")
            raise err
        else:
            return llm_resp_stream

    def invoke_streams_endpoint(self, request):
        content_type = "application/json"
        payload = json.dumps(request, ensure_ascii=False)

        resp = self.client.invoke_endpoint_with_response_stream(
            EndpointName=self.config.endpoint_name,
            ContentType=content_type,
            Body=payload,
        )

        logger.info(resp['ResponseMetadata'])
        event_stream = iter(resp['Body'])

        return event_stream
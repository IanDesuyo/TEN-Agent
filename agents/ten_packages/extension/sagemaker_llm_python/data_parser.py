from typing import Union, List, Dict
from rte import Data
from .sagemaker_llm import SageMakerLLM
from .log import logger
from .property import PUNCUTATIONS
from .property import *

class DataParserBase:
    def __init__(self, chat_template: str='') -> None:
        self.chat_template = chat_template
        self.language = None

    @property
    def language(self) -> str:
        return self._language

    @language.setter
    def language(self, new_lang: str) -> None:
        self._language = new_lang

    @staticmethod
    def get_properties(data: Data, properties: List[str]):
        result = {}
        for property in properties:
            value = None
            try:
                if property not in DATA_IN_TYPES:
                    logger.warning(f"property[{property}] not in DATA_IN_TYPES[{DATA_IN_TYPES}]")

                value = getattr(data, f"get_property_{DATA_IN_TYPES[property]}")(property)
            except Exception as err:
                logger.debug(f"GetProperty {property} failed, err: {err}")

            result[property] = value
        return result

    def format_user_input(self, input_text: str) -> Union[str, None]:
        if not input_text:
            return None

        if self.chat_template:
            try:
                return self.chat_template.format(input_text=input_text)
            except Exception as err:
                logger.exception(f"Apply user template failed, err: {err}. Chat template disabled.")
                self.chat_template = None

        return input_text


class DataParserChat(DataParserBase):
    def parse(self, data: Data, bedrock_llm) -> Union[str, None]:
        properties = self.get_properties(data, [
            DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL,
            DATA_IN_TEXT_DATA_PROPERTY_TEXT
        ])

        if not properties[DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL]:
            logger.info("ignore non-final input")
            return

        if not properties[DATA_IN_TEXT_DATA_PROPERTY_TEXT]:
            logger.info("ignore empty text")
            return

        return self.format_user_input(input_text=properties[DATA_IN_TEXT_DATA_PROPERTY_TEXT])


class DataParserTranslate(DataParserBase):
    def __init__(self, chat_template: str = '') -> None:
        super().__init__(chat_template)

    def parse(self, data: Data, bedrock_llm) -> Union[str, None]:
        properties = self.get_properties(
            data,
            [
                DATA_IN_TEXT_DATA_PROPERTY_LANGUAGE,
                DATA_IN_TEXT_DATA_PROPERTY_TEXT,
                DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL,
                DATA_IN_TEXT_DATA_PROPERTY_TEXT_STABLE,
                DATA_IN_TEXT_DATA_PROPERTY_TEXT_NON_STABLE
            ]
        )

        if properties[DATA_IN_TEXT_DATA_PROPERTY_LANGUAGE]:
            self.language = properties[DATA_IN_TEXT_DATA_PROPERTY_LANGUAGE]

        return self.parse_without_stable(properties)

    def parse_without_stable(self, properties: Dict) -> Union[str, None]:
        if not properties[DATA_IN_TEXT_DATA_PROPERTY_IS_FINAL]:
            logger.info("Ignore non-final input")
            return None

        if not properties[DATA_IN_TEXT_DATA_PROPERTY_TEXT]:
            logger.info("Ignore empty text")
            return None

        return self.format_user_input(input_text=properties[DATA_IN_TEXT_DATA_PROPERTY_TEXT])

from threading import Thread
from rte import (
    Extension,
    RteEnv,
    Cmd,
    Data,
    StatusCode,
    CmdResult,
    MetadataInfo,
)
from .sagemaker_llm_config import SageMakerLLMConfig
from .sagemaker_llm import SageMakerLLM
from .data_parser import *
from .log import logger
from .property import *
from .utils import *

class SageMakerLLMExtension(Extension):
    memory = []
    max_memory_length = 10
    outdate_ts = 0
    sagemaker_llm = None

    def on_start(self, rte: RteEnv) -> None:
        logger.info("SageMakerLLMExtension on_start")
        # Prepare configuration
        llm_config = SageMakerLLMConfig.default_config()
        try:
            endpoint_name = rte.get_property_string(PROPERTY_ENDPOINT_NAME).strip()
            if not endpoint_name:
                raise ValueError(f"GetProperty {PROPERTY_ENDPOINT_NAME} failed, err: empty value.")
            llm_config.endpoint_name = endpoint_name
        except Exception as err:
            logger.debug(f"GetProperty {PROPERTY_ENDPOINT_NAME} failed, err: {err}.")
            raise err

        for optional_str_param in [PROPERTY_REGION, PROPERTY_ACCESS_KEY, PROPERTY_SECRET_KEY,
            PROPERTY_ENGINE, PROPERTY_MODEL, PROPERTY_PROMPT, PROPERTY_MODE, PROPERTY_INPUT_LANGUAGE,
            PROPERTY_OUTPUT_LANGUAGE, PROPERTY_CHAT_TEMPLATE]:
            try:
                value = rte.get_property_string(optional_str_param).strip()
                if value:
                    llm_config.__setattr__(optional_str_param, value)
            except Exception as err:
                logger.debug(f"GetProperty optional {optional_str_param} failed, err: {err}. Using default value: {llm_config.__getattribute__(optional_str_param)}")

        for optional_float_param in [PROPERTY_TEMPERATURE, PROPERTY_TOP_P]:
            try:
                value = rte.get_property_float(optional_float_param)
                if value:
                    llm_config.__setattr__(optional_float_param, value)
            except Exception as err:
                logger.debug(f"GetProperty optional {optional_float_param} failed, err: {err}. Using default value: {llm_config.__getattribute__(optional_float_param)}")

        try:
            max_tokens = rte.get_property_int(PROPERTY_MAX_TOKENS)
            if max_tokens > 0:
                llm_config.max_tokens = int(max_tokens)
        except Exception as err:
            logger.debug(
                f"GetProperty optional {PROPERTY_MAX_TOKENS} failed, err: {err}. Using default value: {llm_config.max_tokens}"
            )

        try:
            greeting = rte.get_property_string(PROPERTY_GREETING)
        except Exception as err:
            logger.debug(
                f"GetProperty optional {PROPERTY_GREETING} failed, err: {err}."
            )

        try:
            prop_max_memory_length = rte.get_property_int(PROPERTY_MAX_MEMORY_LENGTH)
            if prop_max_memory_length >= 0:
                self.max_memory_length = int(prop_max_memory_length)
        except Exception as err:
            logger.debug(
                f"GetProperty optional {PROPERTY_MAX_MEMORY_LENGTH} failed, err: {err}."
            )

        llm_config.validate()

        # Create SageMakerLLM instance
        try:
            self.sagemaker_llm = SageMakerLLM(llm_config)
            logger.info(
                f"newSageMakerLLM succeed, max_tokens: {llm_config.max_tokens}, endpoint: {llm_config.endpoint_name}, mode: {llm_config.mode}, chat template: [{llm_config.chat_template}]"
            )
        except Exception as err:
            logger.exception(f"newSageMakerLLM failed, err: {err}")

        if llm_config.mode == 'translate':
            self.input_data_parser = DataParserTranslate(chat_template=llm_config.chat_template)
        else:
            self.input_data_parser = DataParserChat(chat_template=llm_config.chat_template)

        # Send greeting if available
        if greeting:
            try:
                output_data = Data.create("text_data")
                output_data.set_property_string(
                    DATA_OUT_TEXT_DATA_PROPERTY_TEXT, greeting
                )
                output_data.set_property_bool(
                    DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, True
                )
                rte.send_data(output_data)
                logger.info(f"greeting [{greeting}] sent")
            except Exception as err:
                logger.info(f"greeting [{greeting}] send failed, err: {err}")
        rte.on_start_done()

    def on_stop(self, rte: RteEnv) -> None:
        logger.info("SageMakerLLMExtension on_stop")
        rte.on_stop_done()

    def on_cmd(self, rte: RteEnv, cmd: Cmd) -> None:
        logger.info("SageMakerLLMExtension on_cmd")
        cmd_json = cmd.to_json()
        logger.info("SageMakerLLMExtension on_cmd json: " + cmd_json)

        cmd_name = cmd.get_name()

        if cmd_name == CMD_IN_FLUSH:
            if self.sagemaker_llm.config.mode != 'translate':
                self.outdate_ts = get_current_time()
                cmd_out = Cmd.create(CMD_OUT_FLUSH)
                rte.send_cmd(cmd_out, None)
                logger.info(f"SageMakerLLMExtension on_cmd sent flush")
            else:
                logger.info(f"SageMakerLLMExtension on_cmd ignore flush in '{self.sagemaker_llm.config.mode}' mode.")
        else:
            logger.info(f"SageMakerLLMExtension on_cmd unknown cmd: {cmd_name}")
            cmd_result = CmdResult.create(StatusCode.ERROR)
            cmd_result.set_property_string("detail", "unknown cmd")
            rte.return_result(cmd_result, cmd)
            return

        cmd_result = CmdResult.create(StatusCode.OK)
        cmd_result.set_property_string("detail", "success")
        rte.return_result(cmd_result, cmd)

    def on_data(self, rte: RteEnv, data: Data) -> None:
        """
        on_data receives data from rte graph.
        current supported data:
          - name: text_data
            example:
            {name: text_data, properties: {text: "hello"}}
        """
        logger.info(f"SageMakerLLMExtension on_data")
        # logger.info(data.to_json())

        input_text = self.input_data_parser.parse(data, self.sagemaker_llm)
        if not input_text:
            return

        # Prepare memory.
        while len(self.memory):
            if len(self.memory) > self.max_memory_length:
                logger.debug(
                    f"pop out first non-system message, reason: memory length limit: `{self.memory[0]}`"
                )
                self.memory.pop(0)
            elif self.memory[0]["role"] == "assistant":
                logger.debug(
                    f"pop out first message, reason: messages can not start with assistant: `{self.memory[0]}`"
                )
                self.memory.pop(0)
            else:
                break

        self.memory.append({"role": "user", "content": input_text })

        # if self.sagemaker_llm.config.mode == 'translate':
        #     self.memory.append({"role": "assistant", "content": [{"text": "Sure, here's the translation result: <translation>"}]})

        def converse_stream_worker(start_time, input_text, memory):
            if self.sagemaker_llm.config.prompt:
                memory = [{"role": "system", "content": self.sagemaker_llm.config.prompt }] + memory

            try:
                logger.info(f"GetConverseStream for input text: [{input_text}] memory: {memory}")

                # Get result from SageMaker
                resp = self.sagemaker_llm.get_stream_resp(memory)
                if not resp:
                    logger.info(
                        f"GetConverseStream for input text: [{input_text}] failed"
                    )
                    return

                sentence = ""
                full_content = ""
                first_sentence_sent = False

                for content in resp:
                    # allow 100ms buffer time, in case interruptor's flush cmd comes just after on_data event
                    if (start_time + 100_000) < self.outdate_ts:
                        logger.info(f"GetConverseStream recv interrupt and flushing for input text: [{input_text}], startTs: {start_time}, outdateTs: {self.outdate_ts}, delta > 100ms")
                        break

                    full_content += content

                    while True:
                        sentence, content, sentence_is_final = parse_sentence(
                            sentence, content
                        )
                        if not sentence or not sentence_is_final:
                            # logger.info(f"sentence [{sentence}] is empty or not final")
                            break
                        logger.info(
                            f"GetConverseStream recv for input text: [{input_text}] got sentence: [{sentence}]"
                        )

                        # send sentence
                        try:
                            output_data = Data.create("text_data")
                            output_data.set_property_string(
                                DATA_OUT_TEXT_DATA_PROPERTY_TEXT, sentence
                            )
                            output_data.set_property_bool(
                                DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, False
                            )
                            rte.send_data(output_data)
                            logger.info(
                                f"GetConverseStream recv for input text: [{input_text}] sent sentence [{sentence}]"
                            )
                        except Exception as err:
                            logger.info(
                                f"GetConverseStream recv for input text: [{input_text}] send sentence [{sentence}] failed, err: {err}"
                            )
                            break

                        sentence = ""
                        if not first_sentence_sent:
                            first_sentence_sent = True
                            logger.info(
                                f"GetConverseStream recv for input text: [{input_text}] first sentence sent, first_sentence_latency {get_current_time() - start_time}ms"
                            )

                if len(full_content.strip()):
                    memory.append(
                        {"role": "assistant", "content": full_content}
                    )
                else:
                    # can not put empty model response into memory
                    logger.error(
                        f"GetConverseStream recv for input text: [{input_text}] failed: empty response [{full_content}]"
                    )
                    return

                # send end of segment
                try:
                    output_data = Data.create("text_data")
                    output_data.set_property_string(
                        DATA_OUT_TEXT_DATA_PROPERTY_TEXT, sentence
                    )
                    output_data.set_property_bool(
                        DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, True
                    )
                    rte.send_data(output_data)
                    logger.info(
                        f"GetConverseStream for input text: [{input_text}] end of segment with sentence [{sentence}] sent"
                    )
                except Exception as err:
                    logger.info(
                        f"GetConverseStream for input text: [{input_text}] end of segment with sentence [{sentence}] send failed, err: {err}"
                    )

            except Exception as e:
                logger.info(
                    f"GetConverseStream for input text: [{input_text}] failed, err: {e}"
                )

        # Start thread to request and read responses from SageMaker
        start_time = get_current_time()
        thread = Thread(
            target=converse_stream_worker, args=(start_time, input_text, self.memory)
        )
        thread.start()
        logger.info(f"SageMakerLLMExtension on_data end")
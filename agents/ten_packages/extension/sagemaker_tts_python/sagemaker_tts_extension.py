from rte import (
    Extension,
    RteEnv,
    Cmd,
    PcmFrame,
    PcmFrameDataFmt,
    Data,
    StatusCode,
    CmdResult,
    MetadataInfo,
)

import queue
import threading
from datetime import datetime
import traceback
from contextlib import closing

from .log import logger
from .sagemaker_wrapper import SageMakerTTSWrapper, SageMakerTTSConfig

PROPERTY_REGION = "region"  # Optional
PROPERTY_ACCESS_KEY = "access_key"  # Optional
PROPERTY_SECRET_KEY = "secret_key"  # Optional
PROPERTY_ENDPOINT = 'endpoint'      # Required
PROPERTY_SAMPLE_RATE = 'sample_rate'  # Optional
PROPERTY_PROMPT_AUDIO = 'prompt_audio' # Optional
PROPERTY_PROMPT_TEXT = 'prompt_text' # Optional
PROPERTY_PROMPT_LANGUAGE = 'prompt_language'    # Optional
PROPERTY_OUTPUT_LANGUAGE = 'output_language'    # Optional
PROPERTY_MODEL_TYPE = 'model_type'    # Optional

class SageMakerTTSExtension(Extension):
    def __init__(self, name: str):
        super().__init__(name)

        self.outdateTs = datetime.now()
        self.stopped = False
        self.thread = None
        self.queue = queue.Queue()
        self.frame_size = None

        self.bytes_per_sample = 2
        self.number_of_channels = 1

    def on_start(self, rte: RteEnv) -> None:
        logger.info("SageMakerTTSExtension on_start")

        sagemaker_tts_config = SageMakerTTSConfig.default_config()

        for optional_param in [PROPERTY_REGION, PROPERTY_ACCESS_KEY, PROPERTY_SECRET_KEY,
                               PROPERTY_ENDPOINT, PROPERTY_SAMPLE_RATE, PROPERTY_PROMPT_AUDIO, 
                               PROPERTY_PROMPT_TEXT, PROPERTY_PROMPT_LANGUAGE, PROPERTY_OUTPUT_LANGUAGE,
                               PROPERTY_MODEL_TYPE]:
            try:
                value = rte.get_property_string(optional_param).strip()
                if value:
                    sagemaker_tts_config.__setattr__(optional_param, value)
            except Exception as err:
                logger.info(f"GetProperty optional {optional_param} failed, err: {err}. Using default value: {sagemaker_tts_config.__getattribute__(optional_param)}")

        sagemaker_tts_config.validate()

        self.sagemaker_tts = SageMakerTTSWrapper(sagemaker_tts_config)
        self.frame_size = int(int(sagemaker_tts_config.sample_rate) * self.number_of_channels * self.bytes_per_sample / 100)

        self.thread = threading.Thread(target=self.async_sagemaker_tts_handler, args=[rte])
        self.thread.start()
        rte.on_start_done()

    def on_stop(self, rte: RteEnv) -> None:
        logger.info("SageMakerTTSExtension on_stop")

        self.stopped = True
        self.queue.put(None)
        self.flush()
        self.thread.join()
        rte.on_stop_done()

    def need_interrupt(self, ts: datetime.time) -> bool:
        return (self.outdateTs - ts).total_seconds() > 1

    def __get_frame(self, data: bytes) -> PcmFrame:
        sample_rate = int(self.sagemaker_tts.config.sample_rate)

        f = PcmFrame.create("pcm_frame")
        f.set_sample_rate(sample_rate)
        f.set_bytes_per_sample(2)
        f.set_number_of_channels(1)

        f.set_data_fmt(PcmFrameDataFmt.INTERLEAVE)
        f.set_samples_per_channel(sample_rate // 100)
        f.alloc_buf(self.frame_size)
        buff = f.lock_buf()
        if len(data) < self.frame_size:
            buff[:] = bytes(self.frame_size)  # fill with 0
        buff[:len(data)] = data
        f.unlock_buf(buff)
        return f

    def async_sagemaker_tts_handler(self, rte: RteEnv):
        while not self.stopped:
            value = self.queue.get()
            if value is None:
                logger.warning("async_sagemaker_tts_handler: exit due to None value got.")
                break

            inputText, ts = value
            if not inputText:
                logger.warning("async_sagemaker_tts_handler: empty input detected.")
                continue

            try:
                audio_stream = self.sagemaker_tts.synthesize(text=inputText, language=self.sagemaker_tts.config.output_language)
                for event in audio_stream:
                    if self.need_interrupt(ts):
                        logger.debug("async_sagemaker_tts_handler: got interrupt cmd, stop sending pcm frame.")
                        break
                    chunk_bytes = event['PayloadPart']['Bytes']
                    f = self.__get_frame(chunk_bytes)
                    rte.send_pcm_frame(f)

            except Exception as e:
                logger.exception(e)
                logger.exception(traceback.format_exc())

    def flush(self):
        logger.info("SageMakerTTSExtension flush")
        while not self.queue.empty():
            self.queue.get()
        self.queue.put(("", datetime.now()))

    def on_data(self, rte: RteEnv, data: Data) -> None:
        logger.info("SageMakerTTSExtension on_data")
        inputText = data.get_property_string("text")
        if not inputText:
            logger.info("ignore empty text")
            return

        is_end = data.get_property_bool("end_of_segment")

        logger.info("on data %s %d", inputText, is_end)
        self.queue.put((inputText, datetime.now()))

    def on_cmd(self, rte: RteEnv, cmd: Cmd) -> None:
        logger.info("SageMakerTTSExtension on_cmd")
        cmd_json = cmd.to_json()
        logger.info("SageMakerTTSExtension on_cmd json: %s", cmd_json)

        cmdName = cmd.get_name()
        if cmdName == "flush":
            self.outdateTs = datetime.now()
            self.flush()
            cmd_out = Cmd.create("flush")
            rte.send_cmd(cmd_out, lambda rte, result: print("SageMakerTTSExtension send_cmd done"))
        else:
            logger.info("unknown cmd %s", cmdName)

        cmd_result = CmdResult.create(StatusCode.OK)
        cmd_result.set_property_string("detail", "success")
        rte.return_result(cmd_result, cmd)

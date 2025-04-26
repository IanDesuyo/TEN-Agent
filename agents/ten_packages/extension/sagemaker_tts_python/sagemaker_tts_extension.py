#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
import traceback

from ten import AsyncTenEnv, AudioFrame, AudioFrameDataFmt
from ten_ai_base.tts import AsyncTTSBaseExtension

from .sagemaker_wrapper import SageMakerTTSConfig, SageMakerTTSWrapper


class SageMakerTTSExtension(AsyncTTSBaseExtension):
    def __init__(self, name: str):
        super().__init__(name)
        self.client = None
        self.config: SageMakerTTSConfig = None
        self.frame_size = None
        self.ten_env = None

    async def on_init(self, ten_env: AsyncTenEnv) -> None:
        await super().on_init(ten_env)
        ten_env.log_debug("on_init")
        self.ten_env = ten_env

    async def on_start(self, ten_env: AsyncTenEnv) -> None:
        await super().on_start(ten_env)
        ten_env.log_debug("on_start")

        self.config = await SageMakerTTSConfig.create_async(ten_env=ten_env)

        self.frame_size = int(int(self.config.sample_rate) * 2 * 1 / 100)
        print("!!!FRAMSIZE!!!", self.frame_size)

        if not self.config.access_key:
            raise ValueError("api_key is required")

        self.client = SageMakerTTSWrapper(self.config)

    async def on_stop(self, ten_env: AsyncTenEnv) -> None:
        await super().on_stop(ten_env)
        ten_env.log_debug("on_stop")

    async def on_deinit(self, ten_env: AsyncTenEnv) -> None:
        await super().on_deinit(ten_env)
        ten_env.log_debug("on_deinit")

    async def on_request_tts(
        self, ten_env: AsyncTenEnv, input_text: str, end_of_segment: bool
    ) -> None:
        try:
            audio_stream = self.client.synthesize(
                text=input_text, language=self.client.config.output_language
            )
            for event in audio_stream:
                chunk = event["PayloadPart"]["Bytes"]
                if chunk:
                    await self.send_audio_out(ten_env, chunk, sample_rate=32000)
                else:
                    ten_env.log_debug("Received empty chunk")

        except Exception:
            ten_env.log_error(f"on_request_tts failed: {traceback.format_exc()}")

    async def on_cancel_tts(self, ten_env: AsyncTenEnv) -> None:
        return await super().on_cancel_tts(ten_env)

    def __get_frame(self, data: bytes) -> AudioFrame:
        sample_rate = int(self.config.sample_rate)

        f = AudioFrame.create("pcm_frame")
        f.set_sample_rate(sample_rate)
        f.set_bytes_per_sample(2)
        f.set_number_of_channels(1)

        f.set_data_fmt(AudioFrameDataFmt.INTERLEAVE)
        f.set_samples_per_channel(160)
        self.ten_env.log_info(
            f"set_samples_per_channel: {160}, frame_size: {self.frame_size}, data size: {len(data)}"
        )
        self.frame_size = len(data)
        f.alloc_buf(self.frame_size)
        buff = f.lock_buf()
        if len(data) < self.frame_size:
            buff[:] = bytes(self.frame_size)  # fill with 0
        buff[: len(data)] = data
        f.unlock_buf(buff)
        return f

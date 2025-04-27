#
#
# Agora Real Time Engagement
# Created by Wei Hu in 2024-08.
# Copyright (c) 2024 Agora IO. All rights reserved.
#
#
import asyncio
import json
import threading

import aiohttp
from ten import Cmd, CmdResult, Data, Extension, StatusCode, TenEnv

MAX_SIZE = 800  # 1 KB limit
OVERHEAD_ESTIMATE = 200  # Estimate for the overhead of metadata in the JSON

CMD_NAME_FLUSH = "flush"
CMD_IN_ON_USER_JOINED = "on_user_joined"
CMD_IN_ON_USER_LEFT = "on_user_left"

TEXT_DATA_TEXT_FIELD = "text"
TEXT_DATA_FINAL_FIELD = "is_final"
TEXT_DATA_STREAM_ID_FIELD = "stream_id"
TEXT_DATA_END_OF_SEGMENT_FIELD = "end_of_segment"
DATA_OUT_TEXT_DATA_PROPERTY_TEXT = "text"
DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT = "end_of_segment"

MAX_CHUNK_SIZE_BYTES = 1024


class MessageSummarizerExtension(Extension):
    def __init__(self, name: str):
        super().__init__(name)
        self.queue = asyncio.Queue()
        self.loop = None
        self.cached_text_map = {}
        self.ten_env = None
        self.channel_id = None
        self.user_id = None

    def push_message(self, role: str, text: str):
        # Function to save user query and llm answer
        self.ten_env.log_info(f"Pushing message with role: {role}, text: {text}")
        # Store messages in a format that can be used for summarization later

        asyncio.run_coroutine_threadsafe(
            self._queue_message(
                {
                    "channel_id": self.channel_id,
                    "user_id": self.user_id,
                    "role": role,
                    "text": text,
                }
            ),
            self.loop,
        )

    def summary(self):
        # Function to summarize conversation
        self.ten_env.log_info("Summarizing conversation")
        if not hasattr(self, "conversation_history"):
            self.ten_env.log_info("No conversation history to summarize")
            return

        self.ten_env.log_info("Conversation history:")
        for message in self.conversation_history:
            self.ten_env.log_info(f"{message['role']}: {message['content']}")

        output_data = Data.create("text_data")
        output_data.set_property_string(TEXT_DATA_TEXT_FIELD, "Summary of conversation")
        output_data.set_property_string(
            DATA_OUT_TEXT_DATA_PROPERTY_TEXT, "Summary of conversation"
        )
        output_data.set_property_bool(
            DATA_OUT_TEXT_DATA_PROPERTY_TEXT_END_OF_SEGMENT, True
        )
        self.ten_env.send_data(output_data)

    def on_init(self, ten_env: TenEnv) -> None:
        ten_env.log_info("on_init")
        ten_env.on_init_done()
        self.ten_env = ten_env

    def on_start(self, ten_env: TenEnv) -> None:
        ten_env.log_info("on_start")

        # TODO: read properties, initialize resources
        self.loop = asyncio.new_event_loop()

        def start_loop():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        threading.Thread(target=start_loop, args=[]).start()

        self.loop.create_task(self._process_queue(ten_env))

        ten_env.on_start_done()

    def on_stop(self, ten_env: TenEnv) -> None:
        ten_env.log_info("on_stop")

        # TODO: clean up resources

        ten_env.on_stop_done()

    def on_deinit(self, ten_env: TenEnv) -> None:
        ten_env.log_info("on_deinit")
        ten_env.on_deinit_done()

    def on_cmd(self, ten_env: TenEnv, cmd: Cmd) -> None:
        cmd_name = cmd.get_name()
        ten_env.log_info("on_cmd name {}".format(cmd_name))

        # TODO: process cmd
        if cmd_name == CMD_IN_ON_USER_JOINED:
            self.channel_id = cmd.get_property_string("channel")
            self.user_id = cmd.get_property_string("user_id")
            ten_env.log_info(
                f"User joined, channel_id: {self.channel_id} user_id: {self.user_id}"
            )

        if cmd_name == CMD_IN_ON_USER_LEFT:
            ten_env.log_info(f"User left, generating summary")
            self.summary()

        cmd_result = CmdResult.create(StatusCode.OK)
        ten_env.return_result(cmd_result, cmd)

    def on_data(self, ten_env: TenEnv, data: Data) -> None:
        """
        on_data receives data from ten graph.
        current suppotend data:
          - name: text_data
            example:
            {"name": "text_data", "properties": {"text": "hello", "is_final": true, "stream_id": 123, "end_of_segment": true}}
        """
        # ten_env.log_debug(f"on_data")
        text = ""
        final = True
        stream_id = 0
        end_of_segment = False

        # Add the raw data type if the data is raw text data
        if data.get_name() == "text_data":
            try:
                text = data.get_property_string(TEXT_DATA_TEXT_FIELD)
            except Exception as e:
                ten_env.log_error(
                    f"on_data get_property_string {TEXT_DATA_TEXT_FIELD} error: {e}"
                )

            try:
                final = data.get_property_bool(TEXT_DATA_FINAL_FIELD)
            except Exception:
                pass

            try:
                stream_id = data.get_property_int(TEXT_DATA_STREAM_ID_FIELD)
            except Exception:
                pass

            try:
                end_of_segment = data.get_property_bool(TEXT_DATA_END_OF_SEGMENT_FIELD)
            except Exception as e:
                ten_env.log_warn(
                    f"on_data get_property_bool {TEXT_DATA_END_OF_SEGMENT_FIELD} error: {e}"
                )

            ten_env.log_info(
                f"on_data {TEXT_DATA_TEXT_FIELD}: {text} {TEXT_DATA_FINAL_FIELD}: {final} {TEXT_DATA_STREAM_ID_FIELD}: {stream_id} {TEXT_DATA_END_OF_SEGMENT_FIELD}: {end_of_segment}"
            )

            # We cache all final text data and append the non-final text data to the cached data
            # until the end of the segment.
            if end_of_segment:
                if stream_id in self.cached_text_map:
                    text = self.cached_text_map[stream_id] + text
                    del self.cached_text_map[stream_id]
                # Push message - assuming stream_id can determine if it's user or assistant
                role = "assistant" if stream_id == 0 else "user"
                self.push_message(role, text)
            else:
                if final:
                    if stream_id in self.cached_text_map:
                        text = self.cached_text_map[stream_id] + text

                    self.cached_text_map[stream_id] = text

        elif data.get_name() == "content_data":
            try:
                text = data.get_property_string(TEXT_DATA_TEXT_FIELD)
            except Exception as e:
                ten_env.log_error(
                    f"on_data get_property_string {TEXT_DATA_TEXT_FIELD} error: {e}"
                )

            try:
                end_of_segment = data.get_property_bool(TEXT_DATA_END_OF_SEGMENT_FIELD)
            except Exception as e:
                ten_env.log_warn(
                    f"on_data get_property_bool {TEXT_DATA_END_OF_SEGMENT_FIELD} error: {e}"
                )

            ten_env.log_info(f"on_data {TEXT_DATA_TEXT_FIELD}: {text}")

            # When we have raw content data, push it to the conversation history
            if end_of_segment and text:
                # Determine role based on content metadata, defaulting to "system"
                role = "system"
                self.push_message(role, text)

    async def _queue_message(self, data: dict):
        await self.queue.put(data)

    async def _process_queue(self, ten_env: TenEnv):
        while True:
            data = await self.queue.get()
            if data is None:
                break
            # process data
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://mggyeaf3knhxlpryzezhgw2b2q0efsyz.lambda-url.us-west-2.on.aws/",
                    json=data,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        ten_env.log_info(f"Response: {result}")
                    else:
                        ten_env.log_error(
                            f"Request failed with status: {response.status}"
                        )
            # Sleep to avoid overwhelming the server
            self.queue.task_done()

            await asyncio.sleep(0.04)

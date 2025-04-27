#
#
# Agora Real Time Engagement
# Created by Wei Hu in 2024-08.
# Copyright (c) 2024 Agora IO. All rights reserved.
#
#
from ten import Addon, TenEnv, register_addon_as_extension


@register_addon_as_extension("message_summarizer")
class MessageSummarizerExtensionAddon(Addon):

    def on_create_instance(self, ten_env: TenEnv, name: str, context) -> None:
        from .extension import MessageSummarizerExtension

        ten_env.log_info("on_create_instance")
        ten_env.on_create_instance_done(MessageSummarizerExtension(name), context)

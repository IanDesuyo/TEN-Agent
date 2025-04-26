from ten import Addon, TenEnv, register_addon_as_extension

from .extension import EXTENSION_NAME
from .log import logger
from .sagemaker_tts_extension import SageMakerTTSExtension


@register_addon_as_extension(EXTENSION_NAME)
class SageMakerTTSExtensionAddon(Addon):
    def on_create_instance(self, ten: TenEnv, addon_name: str, context) -> None:
        logger.info("on_create_instance")
        ten.on_create_instance_done(SageMakerTTSExtension(addon_name), context)

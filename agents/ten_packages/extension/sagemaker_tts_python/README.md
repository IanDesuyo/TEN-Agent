### Original Author: [Chen188/TEN-Agent](https://github.com/Chen188/TEN-Agent/tree/amazon-aio/agents/addon/extension/sagemaker_tts_python)

## Amazon SageMaker TTS Extension

### Configurations

You can config this extension by providing following environments:

| Env                   | Required | Default   | Notes                                                                                                                                                                                                                                                                                                                                                             |
| --------------------- | -------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AWS_REGION            | No       | us-east-1 | The Region of Amazon SageMaker service you want to use.                                                                                                                                                                                                                                                                                                           |
| AWS_TTS_ACCESS_KEY_ID | No       | -         | Access Key of your IAM User, make sure you've set proper permissions to [invoke SageMaker](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpointWithResponseStream.html). Will use default credentials provider if not provided. Check [document](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). |
| AWS_SECRET_ACCESS_KEY | No       | -         | Secret Key of your IAM User, make sure you've set proper permissions to [invoke SageMaker](https://docs.aws.amazon.com/sagemaker/latest/APIReference/API_runtime_InvokeEndpointWithResponseStream.html). Will use default credentials provider if not provided. Check [document](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html). |

### Properties

| Property        | Required | Default    | Notes                                                                  |
| --------------- | -------- | ---------- | ---------------------------------------------------------------------- |
| endpoint        | Yes      | -          | The SageMaker Endpoint name                                            |
| sample_rate     | No       | 32000      | Sample Rate of output PCM audio                                        |
| prompt_audio    | Yes      | -          | Reference audio file path. For GPT-Sovits it can be a S3, or local dir |
| prompt_text     | Yes      | -          | Text of the reference audio                                            |
| prompt_language | Yes      | -          | Language of the reference audio                                        |
| output_language | Yes      | -          | Output audio's language                                                |
| model_type      | No       | gpt_sovits | Currently, only `gpt_sovits` is supported.                             |

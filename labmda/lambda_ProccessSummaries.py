import json
import os
import boto3
import urllib3
from boto3.dynamodb.conditions import Key
import io
# 初始化 DynamoDB 和 S3
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME')
target_url = os.environ.get('TARGET_URL')
s3_bucket = os.environ.get('S3_BUCKET_NAME')
s3_prefix = os.environ.get('S3_PREFIX', 'logs/')
api_key = os.environ.get('API_KEY')

table = dynamodb.Table(table_name)
http = urllib3.PoolManager()
s3 = boto3.client('s3')

def lambda_handler(event, context):
    print(event)
    try:
        body = json.loads(event.get('body', '{}'))
        channel_id = body.get('channel_id')
        if not channel_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing channel_id'})
            }
        
        # 查詢 DynamoDB
        response = table.query(
            KeyConditionExpression=Key('id').eq(channel_id)
        )
        
        items = response.get('Items', [])
        
        messages = []
        for item in items:
            role = item.get('role', '')
            raw_text = item.get('text', '')
            #readable_text = bytes(raw_text, "utf-8").decode("unicode_escape")
            messages.append({
                'role': role,
                'message': raw_text
            })
        
        payload = {
            "inputs": {},
            "query": json.dumps(messages, ensure_ascii=False),
            "response_mode": "blocking",
            "conversation_id": "",
            "user": channel_id,
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
        
        # 先確保 payload 是乾淨的 bytes
        encoded_payload = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode('utf-8')

        # 把 JSON 包成 BytesIO（更符合 streaming 標準）
        payload_stream = io.BytesIO(encoded_payload)

        # Streaming 發送 request
        post_response = http.request(
            "POST",
            target_url,
            body=payload_stream,
            headers=headers,
            timeout=urllib3.util.Timeout(connect=30, read=600.0),
            preload_content=False
        )
        
        # 成功才存成 .html
        if 200 <= post_response.status < 300:
            # ⭐ 用 streaming 方式讀取
            answer = ""
            for chunk in post_response.stream():
                print(chunk)
                chunk_text = chunk.decode('utf-8')
                print(chunk_text)
                chunk_text = chunk_text.replace('data:', '').strip()
                chunk_data = json.loads(chunk_text)

                if chunk_data.get('event') == 'message':
                    answer += chunk_data.get('answer', '')

                elif chunk_data.get("event") == "workflow_finished":
                    break

            post_response.release_conn()  # ⭐ 記得釋放連線
            
            html_content = "<h1>Chat History:</h1><br>" + "<br>".join([f"{m['role']}: {m['message']}" for m in messages]) + "<br><br>" + "<h1>Summary:</h1><br>" + answer
            print(html_content)
            s3_key = f"{s3_prefix}{channel_id}.html"
            
            s3.put_object(
                Bucket=s3_bucket,
                Key=s3_key,
                Body=html_content.encode('utf-8'),
                ContentType='text/html; charset=utf-8'
            )
            
            presigned_url = s3.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': s3_bucket,
                    'Key': s3_key
                },
                ExpiresIn=3600
            )
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Data posted and HTML file saved to S3',
                    'presigned_url': presigned_url
                })
            }
        else:
            post_response.release_conn()  # ⭐ 錯誤也要記得釋放連線
            return {
                'statusCode': post_response.status,
                'body': json.dumps({
                    'error': 'Failed to post data (stream)',
                    'response': post_response.data.decode('utf-8')
                })
            }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

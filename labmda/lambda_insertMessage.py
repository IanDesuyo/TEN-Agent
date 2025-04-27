import json
import os
import boto3
from datetime import datetime, timedelta, timezone

# 初始化 DynamoDB
dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('DYNAMODB_TABLE_NAME')
table = dynamodb.Table(table_name)

# 定義 UTC+8 的時區
taipei_tz = timezone(timedelta(hours=8))

def lambda_handler(event, context):
    print(event)
    try:
        # 從 Lambda URL 收到的 body
        body = json.loads(event.get('body', '{}'))
        
        # 檢查必填欄位
        if 'channel_id' not in body:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing channel_id'})
            }
        
        now = datetime.now(taipei_tz)
        timestamp_ms = int(now.timestamp() * 1000)  # 轉成毫秒數
        body['timestamp'] = timestamp_ms
        
        # 重新組成 DynamoDB Item
        item = {
            'id': body.pop('channel_id'),
            'timestamp': body.pop('timestamp'),
            **body  # 把剩下的欄位全部攤開塞進去
        }
        print(item)
        # 寫入 DynamoDB
        table.put_item(Item=item)
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Item saved successfully', 'item': item})
        }
    except Exception as e:
        print("ERROR", e)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

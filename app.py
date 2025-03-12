import requests
import json
import threading
import tiktoken

# 初始化编码器
encoder = tiktoken.get_encoding("cl100k_base")

class ChatCLI:



    def load_config(self):
        try:
            with open('config.json', encoding='utf-8') as f:
                config = json.load(f)
                try:
                    config['temperature'] = float(config.get('temperature', 0.7))
                    config['max_tokens'] = int(config.get('max_tokens', 80000))
                    if 'seed' in config and config['seed'] is not None:
                        config['seed'] = int(config['seed'])
                except (ValueError, TypeError) as e:
                    print(f'配置类型错误: {str(e)}')
        except Exception as e:
            print(f'配置加载错误: {str(e)}')

    def get_ai_response(self, prompt):
        try:
            with open('config.json', encoding='utf-8') as f:
                config = json.load(f)

            response = requests.post(
                url=f"{config['api_base']}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config['api_key']}"
                },
                json={
                    "model": config['model_name'],
                    "messages": [
                        {"role": "system", "content": config.get('system_prompt', '')} if config.get('system_prompt') else None,
                        {"role": "user", "content": prompt}
                    ],
                    "stream": True,
                    "temperature": config.get('temperature', 0.7),
                    "max_tokens": config.get('max_tokens', 80000),
                    "stop": config.get('stop', None),
                    "top_p": config.get('top_p', 1),
                    "seed": config.get('seed', None)
                },
                stream=True,
                timeout=30
            )
            response.raise_for_status()

            buffer = b''
            start_time = time.time()
            first_token_time = None
            last_token_time = None
            token_count = 0
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    buffer += chunk
                    
                    while True:
                        if b'\n' not in buffer:
                            break
                        line, buffer = buffer.split(b'\n', 1)
                        
                        if not line.strip():
                            continue
                        
                        if not line.startswith(b'data: '):
                            continue
                        
                        json_str = line[6:].decode('utf-8')
                        
                        if json_str.strip() == '[DONE]':
                            break
                        
                        try:
                            data = json.loads(json_str)
                            if 'choices' in data and data['choices']:
                                delta = data['choices'][0].get('delta', {})
                                if 'content' in delta:
                                    current_time = time.time()
                                    if not first_token_time:
                                        first_token_time = current_time
                                    else:
                                        last_token_time = current_time
                                    token_count += len(encoder.encode(delta['content']))
                                    print(delta['content'], end='', flush=True)
                        except json.JSONDecodeError:
                            continue

            print('\n')
            if token_count > 0:
                total_time = time.time() - start_time
                first_delay = (first_token_time - start_time) * 1000 if first_token_time else 0
                non_first_delay = (last_token_time - first_token_time) * 1000 if last_token_time and first_token_time else 0
                non_first_tokens = max(token_count - 1, 0)
                
                print(f"输入token数\t{len(encoder.encode(prompt))}")
                print(f"输出token数\t{token_count}")
                print(f"总时长(s)\t{total_time:.2f}")
                print(f"首token延迟(ms)\t{first_delay:.1f}")
                print(f"非首token延迟(ms)\t{non_first_delay / non_first_tokens if non_first_tokens >0 else 0:.1f}")
                print(f"吞吐(Tokens/s)\t{token_count / total_time:.1f}")
        except Exception as e:
            print(f'API错误: {str(e)}')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AI命令行助手')
    parser.add_argument('prompt', help='用户输入的查询内容')
    args = parser.parse_args()
    
    cli = ChatCLI()
    cli.get_ai_response(args.prompt)
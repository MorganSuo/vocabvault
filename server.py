"""
VocabVault 后端 - Flask
提供 / 返回前端页面，/api/search 查词（优先 Free Dictionary API，回退 MiniMax）
"""
import os
import re
import json
import requests
from flask import Flask, request, jsonify, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE, static_url_path='')

# 从环境变量读取，Render 上可配置
MINIMAX_API_KEY = os.environ.get('MINIMAX_API_KEY', '')

FREE_DICT_URL = 'https://api.dictionaryapi.dev/api/v2/entries/en'
MINIMAX_URL = 'https://api.minimax.io/anthropic/v1/messages'


def transform_free_dictionary(data):
    """将 Free Dictionary API 响应转为前端统一格式"""
    first = data[0] if isinstance(data, list) else data
    if not first or not first.get('word'):
        return None
    audio_url = None
    for p in (first.get('phonetics') or []):
        if p.get('audio'):
            audio_url = p['audio'] if p['audio'].startswith('http') else 'https:' + p['audio']
            break
    definitions = []
    for m in first.get('meanings', []):
        for d in m.get('definitions', []):
            definitions.append({
                'meaning': d.get('definition', ''),
                'example': d.get('example', ''),
                'translation': ''
            })
    synonyms = []
    for m in first.get('meanings', []):
        for d in m.get('definitions', []):
            synonyms.extend(d.get('synonyms', []))
    synonyms = list(dict.fromkeys(synonyms))[:10]
    first_meaning = (first.get('meanings') or [{}])[0]
    return {
        'word': first['word'],
        'phonetic': first.get('phonetic') or (first.get('phonetics') or [{}])[0].get('text', ''),
        'partOfSpeech': first_meaning.get('partOfSpeech', 'word'),
        'definitions': definitions or [{'meaning': '暂无释义', 'example': '', 'translation': ''}],
        'synonyms': synonyms,
        'usage': first.get('origin', ''),
        'audioUrl': audio_url
    }


@app.route('/')
def index():
    return send_from_directory(BASE, 'index.html')


@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': '请提供查询内容'}), 400

    # 单词则优先 Free Dictionary API
    if re.match(r"^[a-zA-Z\-']+$", query):
        try:
            r = requests.get(f'{FREE_DICT_URL}/{query}', timeout=8)
            if r.status_code == 200:
                out = transform_free_dictionary(r.json())
                if out:
                    return jsonify(out)
        except Exception as e:
            if getattr(e, 'response', None) and getattr(e.response, 'status_code', None) != 404:
                print('Free Dictionary API 失败，回退 MiniMax:', e)

    # MiniMax
    if not MINIMAX_API_KEY:
        return jsonify({'error': '未配置 MINIMAX_API_KEY'}), 500

    prompt = f'''你是一个专业的英语词典和语言学习助手。请为用户提供关于"{query}"的详细信息，包括：
1. 单词/短语及其正确拼写
2. 音标（IPA格式）
3. 词性（名词/动词/形容词/副词/短语等）
4. 详细的中文释义
5. 至少3个英文例句（带中文翻译）
6. 同义词
7. 使用场景说明

请以JSON格式返回结果，格式如下：
{{
  "word": "查询的单词或短语",
  "phonetic": "音标",
  "partOfSpeech": "词性",
  "definitions": [
    {{ "meaning": "释义内容", "example": "例句", "translation": "例句翻译" }}
  ],
  "synonyms": ["同义词1", "同义词2"],
  "usage": "使用说明"
}}'''

    try:
        r = requests.post(
            MINIMAX_URL,
            json={
                'model': 'MiniMax-M2.5',
                'max_tokens': 2000,
                'system': '你是一个专业的英语词典和语言学习助手，擅长解释单词、短语和表达方式的含义、用法和例句。',
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}],
                'temperature': 1.0
            },
            headers={
                'x-api-key': MINIMAX_API_KEY,
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01'
            },
            timeout=30
        )
        r.raise_for_status()
        resp = r.json()
        content_list = resp.get('content') or []
        content = ''
        for item in content_list:
            if item.get('type') == 'text':
                content = item.get('text', '')
                break
        if not content:
            return jsonify({'error': '未找到文本内容'}), 500
        # 解析 JSON 块
        m = re.search(r'```json\s*([\s\S]*?)\s*```', content)
        if m:
            return jsonify(json.loads(m.group(1)))
        m = re.search(r'\{[\s\S]*\}', content)
        if m:
            return jsonify(json.loads(m.group(0)))
        return jsonify({'word': query, 'rawResponse': content, 'isRawFormat': True})
    except requests.RequestException as e:
        err = e.response.json() if hasattr(e, 'response') and e.response is not None else {}
        msg = err.get('error', {}).get('message', str(e))
        return jsonify({'error': f'API调用失败: {msg}'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)

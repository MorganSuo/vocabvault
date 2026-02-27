"""
VocabVault 后端 - Flask
提供 / 返回前端页面，/api/search 查词（优先 Free Dictionary API，回退 MiniMax）
支持云端同步（Supabase）
"""
import os
import re
import json
import requests
from urllib.parse import quote
from flask import Flask, request, jsonify, send_from_directory
from supabase import create_client, Client

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE, static_url_path='')

# 从环境变量读取，Render 上可配置
MINIMAX_API_KEY = os.environ.get('MINIMAX_API_KEY', '')

# Supabase 配置
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# 初始化 Supabase 客户端（如果配置了）
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f'Supabase 初始化成功, URL: {SUPABASE_URL[:30]}...')
    except Exception as e:
        print('Supabase 初始化失败:', e)
else:
    print('Supabase 未配置: SUPABASE_URL 或 SUPABASE_KEY 为空')

FREE_DICT_URL = 'https://api.dictionaryapi.dev/api/v2/entries/en'
MINIMAX_URL = 'https://api.minimax.io/anthropic/v1/messages'

# 部分环境要求带 User-Agent
FREE_DICT_HEADERS = {'User-Agent': 'VocabVault/1.0 (https://vocabvault-k72p.onrender.com)'}


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


@app.route('/api/health')
def health():
    return jsonify({'ok': True, 'service': 'vocabvault'})


@app.route('/api/search', methods=['POST'])
def search():
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': '请提供查询内容'}), 400

    # 先尝试 Free Dictionary API（单词和短语都试，短语可能 404）
    encoded = quote(query, safe="")
    try:
        r = requests.get(
            f'{FREE_DICT_URL}/{encoded}',
            timeout=10,
            headers=FREE_DICT_HEADERS
        )
        if r.status_code == 200:
            out = transform_free_dictionary(r.json())
            if out:
                return jsonify(out)
    except requests.RequestException as e:
        err_msg = getattr(e, 'message', str(e))
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_msg = e.response.text[:200] if e.response.text else str(e)
            except Exception:
                pass
        print('Free Dictionary API 失败:', err_msg)
    except Exception as e:
        print('Free Dictionary 解析异常:', e)

    # 短语/表达或 Free Dictionary 未命中：使用 MiniMax
    if not MINIMAX_API_KEY:
        return jsonify({
            'error': '短语与表达类查询需在 Render 环境变量中配置 MINIMAX_API_KEY 后才能使用。'
        }), 200

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
                'system': [{'type': 'text', 'text': '你是一个专业的英语词典和语言学习助手，擅长解释单词、短语和表达方式的含义、用法和例句。'}],
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}],
                'temperature': 1.0
            },
            headers={
                'Authorization': 'Bearer ' + MINIMAX_API_KEY,
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        # 打印响应以便调试
        print('MiniMax 响应状态:', r.status_code)
        if r.status_code != 200:
            print('MiniMax 错误响应:', r.text[:500])
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
        err_body = ''
        if hasattr(e, 'response') and e.response is not None:
            err_body = e.response.text[:300]
        # 返回更详细的错误信息给前端
        return jsonify({
            'error': f'短语查询暂时不可用。请确认已在 Render 环境变量中配置 MINIMAX_API_KEY。错误详情: {str(e)[:100]}'
        }), 200  # 返回 200 让前端能显示错误信息


# ========== 数据同步 API ==========

@app.route('/api/sync/load', methods=['GET'])
def load_data():
    """加载云端数据"""
    print('load_data called, supabase is:', supabase)
    if not supabase:
        return jsonify({'error': 'Cloud sync not configured'}), 500
    try:
        response = supabase.table('vocabulary').select('*').order('created_at', desc=True).execute()
        vocabulary = response.data or []
        print('Loaded vocabulary count:', len(vocabulary))
        tags_response = supabase.table('custom_tags').select('*').execute()
        custom_tags = tags_response.data or []
        return jsonify({
            'vocabulary': vocabulary,
            'customTags': [t['tag'] for t in custom_tags]
        })
    except Exception as e:
        print('加载数据失败:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sync/save', methods=['POST'])
def save_data():
    """保存数据到云端（完整覆盖）"""
    print('save_data called, supabase:', supabase)
    if not supabase:
        return jsonify({'error': 'Cloud sync not configured'}), 500
    data = request.get_json() or {}
    vocabulary = data.get('vocabulary', [])
    custom_tags = data.get('customTags', [])
    print('Saving vocabulary count:', len(vocabulary))
    print('Saving custom_tags:', custom_tags)
    try:
        # Clear and insert vocabulary one by one
        supabase.table('vocabulary').delete().neq('id', 'x' * 100).execute()
        for v in vocabulary:
            supabase.table('vocabulary').insert(v).execute()
        
        # Clear and insert custom tags
        supabase.table('custom_tags').delete().neq('id', -1).execute()
        for t in custom_tags:
            supabase.table('custom_tags').insert({'tag': t}).execute()
        
        return jsonify({'ok': True})
    except Exception as e:
        print('保存数据失败:', e)
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500


@app.route('/api/sync/add', methods=['POST'])
def add_word():
    """添加单个词汇"""
    if not supabase:
        return jsonify({'error': 'Cloud sync not configured'}), 500
    word = request.get_json() or {}
    try:
        supabase.table('vocabulary').insert(word).execute()
        return jsonify({'ok': True})
    except Exception as e:
        print('添加词汇失败:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sync/delete/<word_id>', methods=['DELETE'])
def delete_word(word_id):
    """删除单个词汇"""
    if not supabase:
        return jsonify({'error': 'Cloud sync not configured'}), 500
    try:
        supabase.table('vocabulary').delete().eq('id', word_id).execute()
        return jsonify({'ok': True})
    except Exception as e:
        print('删除词汇失败:', e)
        return jsonify({'error': str(e)}), 500


@app.route('/api/sync/update', methods=['POST'])
def update_word():
    """更新词汇"""
    if not supabase:
        return jsonify({'error': 'Cloud sync not configured'}), 500
    data = request.get_json() or {}
    word_id = data.get('id')
    updates = {k: v for k, v in data.items() if k != 'id'}
    try:
        supabase.table('vocabulary').update(updates).eq('id', word_id).execute()
        return jsonify({'ok': True})
    except Exception as e:
        print('更新词汇失败:', e)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 3000))
    app.run(host='0.0.0.0', port=port)

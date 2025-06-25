from flask import Flask, request, jsonify, render_template, send_from_directory
from openai import OpenAI
import os
import base64
from datetime import datetime
import json
from werkzeug.utils import secure_filename
# Renderでは環境変数を直接設定するため、dotenvは不要

# Flaskアプリ
app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# OpenAIクライアント
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# データ保存用（実際の実装ではDBを使用）
# ここでは簡易的にメモリに保存
user_history = {}

# ルートページ（メイン画面を直接表示）
@app.route('/')
def index():
    return render_template('main.html')

# Service Worker
@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

# Manifest
@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')

# 静的ファイル配信
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

# 画像アップロードと解析
@app.route('/upload', methods=['POST'])
def upload():
    try:
        # フォームデータ取得（固定値を使用）
        school_id = request.form.get('school_id', 'default_school')
        user_id = request.form.get('user_id', 'default_user')
        
        if 'file' not in request.files:
            return jsonify({"error": "ファイルがありません"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "ファイルが選択されていません"}), 400
        
        # 画像データを読み込み
        image_data = file.read()
        
        # base64エンコード
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # GPT Vision APIで画像解析
        prompt = """
        この画像に写っている問題を分析して、中学生から高校生の学習者に適した教育的な指導をしてください。

【絶対に守ること】
- 計算しなくていいから、解き方の手順だけ教えてください
- 日本の中学生や高校生の知識の範囲内で説明してください

【数式の表記ルール（MathJax対応）】
インライン数式は $ $ で囲む、ディスプレイ数式は $$ $$ で囲む

- 分数：$\\frac{分子}{分母}$ 例：$\\frac{x}{2}$
- 累乗：$x^2$, $x^{10}$, $a^{n+1}$
- 平方根：$\\sqrt{2}$, $\\sqrt{x+1}$, $\\sqrt[3]{8}$（3乗根）
- ギリシャ文字：$\\alpha$, $\\beta$, $\\gamma$, $\\theta$, $\\pi$, $\\omega$
- 三角関数：$\\sin \\theta$, $\\cos \\theta$, $\\tan \\theta$
- 対数：$\\log_2 x$, $\\ln x$
- 総和：$\\sum_{i=1}^{n} i^2$
- 積分：$\\int_0^1 x^2 dx$
- ベクトル：$\\vec{AB}$ または $\\overrightarrow{AB}$
- 極限：$\\lim_{x \\to \\infty} \\frac{1}{x}$
- 行列：$\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}$
- 不等号：$\\leq$, $\\geq$, $\\neq$

【表示形式】
- 考え方と手順のみ表示
- 重要な数式は $$...$$ で中央揃え表示

まず画像の内容を詳しく分析し、問題文を正確に読み取ってから指導を開始してください。
"""

        gpt_response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "auto"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        explanation_text = gpt_response.choices[0].message.content.strip()
        
        # 履歴に保存（実際の実装ではDBに保存）
        if user_id not in user_history:
            user_history[user_id] = []
        
        history_item = {
            "school_id": school_id,
            "image_base64": base64_image,
            "explanation": explanation_text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        user_history[user_id].append(history_item)
        
        # 履歴を最新20件に制限
        if len(user_history[user_id]) > 20:
            user_history[user_id] = user_history[user_id][-20:]
        
        return jsonify({
            "success": True,
            "explanation": explanation_text
        })
        
    except Exception as e:
        print(f"エラー発生: {str(e)}")
        return jsonify({
            "error": "画像の解析に失敗しました。もう一度お試しください。",
            "details": str(e)
        }), 500

# 履歴取得
@app.route('/history', methods=['GET'])
def get_history():
    # 固定ユーザーIDを使用
    user_id = request.args.get('user_id', 'default_user')
    
    # ユーザーの履歴を取得（最新順）
    history = user_history.get(user_id, [])
    return jsonify(history[::-1])  # 新しい順に返す

# ヘルスチェック
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "勉強サポートアプリは正常に動作しています"})

# エラーハンドラー
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "ファイルサイズが大きすぎます。16MB以下のファイルを選択してください。"}), 413

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "サーバーエラーが発生しました。しばらくしてからもう一度お試しください。"}), 500

if __name__ == "__main__":
    # 必要なディレクトリの作成
    os.makedirs('static', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # 開発用サーバー起動
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
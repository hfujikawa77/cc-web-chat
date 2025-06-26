#!/usr/bin/env python3

import http.server
import socketserver
import json
import subprocess
import os
import re
import uuid
import argparse
import pkg_resources
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# 起動時の作業ディレクトリを保存（パッケージとして起動された場合のルート）
STARTUP_DIRECTORY = os.getcwd()

# インスタンス識別用のID（プロセスごとに一意）
INSTANCE_ID = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"

# Configuration from environment variables
PORT = int(os.getenv('PORT', 8081))
HOST = os.getenv('HOST', '0.0.0.0')
MAX_MESSAGES_PER_SESSION = int(os.getenv('MAX_MESSAGES_PER_SESSION', 50))
CONTEXT_WINDOW_SIZE = int(os.getenv('CONTEXT_WINDOW_SIZE', 5))
MAX_SESSIONS = int(os.getenv('MAX_SESSIONS', 100))
CLAUDE_TIMEOUT = int(os.getenv('CLAUDE_TIMEOUT', 60))
CLAUDE_STREAM_TIMEOUT = int(os.getenv('CLAUDE_STREAM_TIMEOUT', 180))
CLAUDE_COMMAND_PREFIX = os.getenv('CLAUDE_COMMAND_PREFIX', 'claude')
ENABLE_DANGEROUS_PERMISSIONS = os.getenv('ENABLE_DANGEROUS_PERMISSIONS', 'true').lower() == 'true'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
ENABLE_DEBUG_LOGS = os.getenv('ENABLE_DEBUG_LOGS', 'true').lower() == 'true'
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'logs/claude_chat.log')
CORS_ALLOW_ORIGIN = os.getenv('CORS_ALLOW_ORIGIN', '*')
ENABLE_CORS = os.getenv('ENABLE_CORS', 'true').lower() == 'true'

# 会話セッションを保持（インスタンスごと）
chat_sessions = {}

# セッションごとの作業ディレクトリを保持（インスタンスごと）
session_directories = {}

class ClaudeChatHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        # favicon.icoのリクエストを処理
        if self.path == '/favicon.ico':
            self.send_response(204)  # No Content
            self.end_headers()
            return
        
        # HTMLファイルのリクエストを処理
        if self.path == '/claude_chat.html' or self.path == '/':
            try:
                # パッケージリソースからHTMLファイルを取得
                import os
                html_path = os.path.join(os.path.dirname(__file__), 'claude_chat.html')
                
                with open(html_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content.encode('utf-8'))
                return
            except FileNotFoundError:
                self.send_error(404, "HTML file not found")
                return
        
        # 通常のGETリクエストを処理
        super().do_GET()
    
    def do_POST(self):
        if self.path == '/api/chat':
            self.handle_chat()
        elif self.path == '/api/chat/stream':
            # ストリーミングAPIを実装
            self.handle_chat_stream()
        elif self.path == '/api/directory/change':
            self.handle_directory_change()
        elif self.path == '/api/directory/info':
            self.handle_directory_info()
        else:
            self.send_error(404, "Not Found")
    
    def handle_chat(self):
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '')
            session_id = data.get('session_id', str(uuid.uuid4()))
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] User ({session_id[:8]}): {user_message}")
            
            # セッション履歴を取得または初期化
            if session_id not in chat_sessions:
                chat_sessions[session_id] = []
                session_directories[session_id] = STARTUP_DIRECTORY  # 起動時ディレクトリを設定
                print(f"[INFO] 新しいセッション作成: {session_id[:8]} (作業ディレクトリ: {session_directories[session_id]})")
            
            history = chat_sessions[session_id]
            
            # セッションの作業ディレクトリ情報を取得
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            
            # ユーザーメッセージを履歴に追加（ディレクトリ情報も含める）
            history.append(f"User: {user_message} [作業ディレクトリ: {current_dir}]")
            
            # コンテキストを構築（設定値に基づく）
            context = "\n".join(history[-CONTEXT_WINDOW_SIZE:])
            
            # Claude Code CLIに送信
            response = self.handle_claude_conversation(user_message, context, session_id)
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Assistant: {response[:100]}...")
            
            # 応答を履歴に追加（ディレクトリ情報も含める）
            history.append(f"Assistant: {response} [作業ディレクトリ: {current_dir}]")
            
            # セッションを保存（設定値に基づく）
            chat_sessions[session_id] = history[-MAX_MESSAGES_PER_SESSION:]
            
            # レスポンスを送信
            result = {
                "response": response,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            import traceback
            error_msg = f"サーバーエラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(traceback.format_exc())
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_msg}, ensure_ascii=False).encode('utf-8'))
    
    def handle_chat_stream(self):
        """ストリーミング対応のチャットハンドラ"""
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '')
            session_id = data.get('session_id', str(uuid.uuid4()))
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Stream User ({session_id[:8]}): {user_message}")
            
            # セッション履歴を取得または初期化
            if session_id not in chat_sessions:
                chat_sessions[session_id] = []
                session_directories[session_id] = STARTUP_DIRECTORY  # 起動時ディレクトリを設定
                print(f"[INFO] 新しいセッション作成: {session_id[:8]} (作業ディレクトリ: {session_directories[session_id]})")
            
            history = chat_sessions[session_id]
            
            # セッションの作業ディレクトリ情報を取得
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            
            # ユーザーメッセージを履歴に追加（ディレクトリ情報も含める）
            history.append(f"User: {user_message} [作業ディレクトリ: {current_dir}]")
            
            # ストリーミングレスポンスのヘッダー設定
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('Connection', 'close')  # 接続を確実に閉じる
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            # 即座にフラッシュ
            self.wfile.flush()
            
            # ストリーミング実行
            final_response = self.handle_claude_stream(user_message, session_id)
            
            # 応答を履歴に追加（ディレクトリ情報も含める）
            history.append(f"Assistant: {final_response} [作業ディレクトリ: {current_dir}]")
            
            # セッションを保存（設定値に基づく）
            chat_sessions[session_id] = history[-MAX_MESSAGES_PER_SESSION:]
            
            # 終了シグナル
            self.wfile.write(b'data: [DONE]\n\n')
            self.wfile.flush()
            
            print(f"[DEBUG] ストリーミング完了: {session_id[:8]}")
            
        except BrokenPipeError:
            print(f"[INFO] クライアント接続切断: {session_id[:8] if 'session_id' in locals() else 'unknown'}")
        except Exception as e:
            import traceback
            error_msg = f"ストリーミングエラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            print(traceback.format_exc())
            
            try:
                error_data = json.dumps({"error": error_msg}, ensure_ascii=False)
                self.wfile.write(f'data: {error_data}\n\n'.encode('utf-8'))
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
            except:
                pass
    
    def handle_claude_stream(self, message, session_id):
        """Claude Code CLIをストリーミング実行"""
        try:
            # セッション履歴を取得してコンテキストを構築
            history = chat_sessions.get(session_id, [])
            
            # 最新の会話コンテキスト（設定値に基づく）を取得
            context_size = CONTEXT_WINDOW_SIZE * 2  # User + Assistant pairs
            recent_context = history[-context_size:] if len(history) > context_size else history[:]
            
            # コンテキストを文字列として構築
            context_str = ""
            if recent_context:
                context_str = "\n\n前の会話の履歴:\n" + "\n".join(recent_context[-6:-1])  # 現在のメッセージ以外
            
            # .mdファイルかどうかをチェック
            is_markdown_request = self.is_markdown_related_request(message)
            
            # セッションの作業ディレクトリを取得
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            directory_context = f"""

重要な作業ディレクトリ情報:
現在の作業ディレクトリ: {current_dir}

注意事項:
- このチャットセッションの作業ディレクトリは '{current_dir}' です
- 全てのファイル操作は '{current_dir}' を基準に実行してください
- Read, Write, Edit, Glob ツールを使用する際は '{current_dir}/' から始まるパスを使用
- ディレクトリ移動やcd コマンドの要求は、現在のディレクトリが '{current_dir}' であることを応答に含めてください
- プロセス実行時の cwd は '{current_dir}' に設定されています"""
            
            # 作業ディレクトリの強力な指示を最初に配置
            working_dir_instruction = f"""🔴 WORKING DIRECTORY: {current_dir} 🔴

重要な作業ディレクトリルール:
1. あなたの現在の作業ディレクトリは {current_dir} です
2. 全てのファイル操作は必ず {current_dir} で実行してください
3. ファイル存在確認は {current_dir} でのみ行ってください
4. 他のディレクトリにあるファイルは無視してください
5. Read, Write, Edit, Glob ツールは {current_dir}/ から始まるパスを使用
6. 作業ディレクトリ外のファイルが存在しても関係ありません

例:
- ファイル作成時: {current_dir}/filename.py を使用
- ファイル確認時: {current_dir} 内のみをチェック
- 「ファイルを作成して」→ まず {current_dir} で存在確認、なければ即座に作成"""

            if is_markdown_request:
                claude_prompt = f"""{working_dir_instruction}

{context_str}

{message}{directory_context}

🔴 絶対に守るべき指示 🔴:
1. 作業ディレクトリは {current_dir} です - これ以外は使用禁止
2. ファイル作成要求時は、まず {current_dir} で存在確認し、なければ即座に作成
3. 他のディレクトリのファイルは完全に無視
4. ファイル操作は必ず {current_dir}/ から始まるフルパスを使用
5. 「ファイルがある」という判断は {current_dir} 内のみで行う
6. 前の会話の文脈を理解して適切に応答
7. .mdファイルの場合はMarkdown記法を使用
8. 日本語で応答してください

重要: {current_dir} 以外のディレクトリのファイルは存在しないものとして扱ってください"""
            else:
                claude_prompt = f"""{working_dir_instruction}

{context_str}

{message}{directory_context}

🔴 絶対に守るべき指示 🔴:
1. 作業ディレクトリは {current_dir} です - これ以外は使用禁止
2. ファイル作成要求時は、まず {current_dir} で存在確認し、なければ即座に作成
3. 他のディレクトリのファイルは完全に無視
4. ファイル操作は必ず {current_dir}/ から始まるフルパスを使用
5. 「ファイルがある」という判断は {current_dir} 内のみで行う
6. 前の会話の文脈を理解して適切に応答
7. ユーザーの選択に応じて適切に実行
8. ファイル読み込み時は実際のソースコードを表示
9. コードブロックを適切にフォーマット
10. 日本語で応答してください

重要: {current_dir} 以外のディレクトリのファイルは存在しないものとして扱ってください"""
            
            print(f"[DEBUG] ストリーミング開始...")
            
            # Claude Code CLIをストリーミングモードで実行
            cmd = [CLAUDE_COMMAND_PREFIX, '-p']
            if ENABLE_DANGEROUS_PERMISSIONS:
                cmd.append('--dangerously-skip-permissions')
            cmd.extend(['--output-format', 'stream-json', '--verbose'])
            
            # 初期状態を送信
            init_data = {
                "type": "init",
                "message": "処理を開始しています...",
                "session_id": session_id
            }
            self.send_stream_data(init_data)
            
            # プロセス実行
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            # 環境変数を設定してディレクトリコンテキストを強化
            env = os.environ.copy()
            env['CLAUDE_WORKING_DIR'] = current_dir
            env['PWD'] = current_dir
            
            process = subprocess.Popen(
                cmd + [claude_prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,  # 無バッファ
                universal_newlines=True,
                cwd=current_dir,
                env=env
            )
            
            full_response = ""
            current_message = ""
            
            # タイムアウト設定
            import signal
            def timeout_handler(signum, frame):
                raise TimeoutError("Claude Code プロセスがタイムアウトしました")
            
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(CLAUDE_STREAM_TIMEOUT)  # 設定値に基づくタイムアウト
            
            try:
                # ストリーミング処理
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                        
                    if output.strip():
                        try:
                            # JSONライン解析
                            line_data = json.loads(output.strip())
                            processed_data = self.process_stream_line(line_data, session_id)
                            
                            if processed_data:
                                self.send_stream_data(processed_data)
                                
                                # メッセージ内容を蓄積
                                if processed_data.get("type") == "assistant" and "content" in processed_data:
                                    current_message = processed_data["content"]
                                    
                        except json.JSONDecodeError as e:
                            print(f"[DEBUG] JSON解析エラー: {e} - Line: {output.strip()}")
                            continue
                            
                # プロセス終了待ち
                return_code = process.wait(timeout=10)
                
            except TimeoutError:
                print(f"[ERROR] Claude Code プロセスタイムアウト")
                process.kill()
                return "⏰ Claude Codeの処理がタイムアウトしました"
            finally:
                signal.alarm(0)  # タイムアウト解除
            
            if return_code == 0:
                if current_message:
                    full_response = current_message
                else:
                    full_response = "処理が完了しました。"
            else:
                stderr_output = process.stderr.read()
                print(f"[ERROR] Claude Code エラー (code: {return_code}): {stderr_output}")
                full_response = f"⚠️ Claude Code エラー:\n{stderr_output}"
                
            return full_response
            
        except Exception as e:
            import traceback
            print(f"[ERROR] ストリーミング実行エラー: {str(e)}")
            print(traceback.format_exc())
            return f"❌ ストリーミング実行エラー: {str(e)}"
    
    def process_stream_line(self, line_data, session_id):
        """ストリームラインデータを処理"""
        line_type = line_data.get("type", "")
        
        if line_type == "system":
            subtype = line_data.get("subtype", "")
            if subtype == "init":
                return {
                    "type": "system",
                    "message": "Claude Code初期化中...",
                    "session_id": session_id,
                    "details": line_data
                }
        elif line_type == "assistant":
            message = line_data.get("message", {})
            content_list = message.get("content", [])
            
            # テキストコンテンツを抽出
            text_content = ""
            for content in content_list:
                if content.get("type") == "text":
                    text_content += content.get("text", "")
            
            if text_content:
                return {
                    "type": "assistant",
                    "content": text_content,
                    "session_id": session_id,
                    "usage": line_data.get("usage", {})
                }
        elif line_type == "result":
            subtype = line_data.get("subtype", "")
            if subtype == "success":
                return {
                    "type": "result",
                    "message": "処理完了",
                    "content": line_data.get("result", ""),
                    "session_id": session_id,
                    "cost": line_data.get("cost_usd", 0),
                    "duration": line_data.get("duration_ms", 0)
                }
        
        return None
    
    def send_stream_data(self, data):
        """ストリームデータを送信"""
        try:
            json_data = json.dumps(data, ensure_ascii=False)
            self.wfile.write(f'data: {json_data}\n\n'.encode('utf-8'))
            self.wfile.flush()
        except Exception as e:
            print(f"[ERROR] ストリーム送信エラー: {e}")
    
    def handle_claude_conversation(self, message, context, session_id):
        """Claude Code CLIとの実際の対話"""
        try:
            # .mdファイルかどうかをチェック
            is_markdown_request = self.is_markdown_related_request(message)
            
            # セッションの作業ディレクトリを取得
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            directory_context = f"""

重要な作業ディレクトリ情報:
現在の作業ディレクトリ: {current_dir}

注意事項:
- このチャットセッションの作業ディレクトリは '{current_dir}' です
- 全てのファイル操作は '{current_dir}' を基準に実行してください
- Read, Write, Edit, Glob ツールを使用する際は '{current_dir}/' から始まるパスを使用
- ディレクトリ移動やcd コマンドの要求は、現在のディレクトリが '{current_dir}' であることを応答に含めてください
- プロセス実行時の cwd は '{current_dir}' に設定されています"""
            
            # 作業ディレクトリの強力な指示を最初に配置
            working_dir_instruction = f"""🔴 WORKING DIRECTORY: {current_dir} 🔴

重要な作業ディレクトリルール:
1. あなたの現在の作業ディレクトリは {current_dir} です
2. 全てのファイル操作は必ず {current_dir} で実行してください
3. ファイル存在確認は {current_dir} でのみ行ってください
4. 他のディレクトリにあるファイルは無視してください
5. Read, Write, Edit, Glob ツールは {current_dir}/ から始まるパスを使用
6. 作業ディレクトリ外のファイルが存在しても関係ありません

例:
- ファイル作成時: {current_dir}/filename.py を使用
- ファイル確認時: {current_dir} 内のみをチェック
- 「ファイルを作成して」→ まず {current_dir} で存在確認、なければ即座に作成"""

            if is_markdown_request:
                # .mdファイル関連の場合はMarkdown記法を使用
                claude_prompt = f"""{working_dir_instruction}

{context}

{message}{directory_context}

🔴 絶対に守るべき指示 🔴:
1. 作業ディレクトリは {current_dir} です - これ以外は使用禁止
2. ファイル作成要求時は、まず {current_dir} で存在確認し、なければ即座に作成
3. 他のディレクトリのファイルは完全に無視
4. ファイル操作は必ず {current_dir}/ から始まるフルパスを使用
5. 「ファイルがある」という判断は {current_dir} 内のみで行う
6. 前の会話の文脈を理解して適切に応答
7. .mdファイルの場合はMarkdown記法を使用
8. 日本語で応答してください

重要: {current_dir} 以外のディレクトリのファイルは存在しないものとして扱ってください"""
            else:
                # 通常のファイルの場合は従来通り
                claude_prompt = f"""{working_dir_instruction}

{context}

{message}{directory_context}

🔴 絶対に守るべき指示 🔴:
1. 作業ディレクトリは {current_dir} です - これ以外は使用禁止
2. ファイル作成要求時は、まず {current_dir} で存在確認し、なければ即座に作成
3. 他のディレクトリのファイルは完全に無視
4. ファイル操作は必ず {current_dir}/ から始まるフルパスを使用
5. 「ファイルがある」という判断は {current_dir} 内のみで行う
6. 前の会話の文脈を理解して適切に応答
7. ユーザーの選択に応じて適切に実行
8. ファイル読み込み時は実際のソースコードを表示
9. コードブロックを適切にフォーマット
10. 日本語で応答してください

重要: {current_dir} 以外のディレクトリのファイルは存在しないものとして扱ってください"""
            
            print(f"[DEBUG] Claude Codeに送信中...")
            print(f"[DEBUG] セッション {session_id[:8]} の作業ディレクトリ: {current_dir}")
            print(f"[DEBUG] メッセージ: {message[:50]}...")
            
            # Claude Code CLIに送信
            cmd = [CLAUDE_COMMAND_PREFIX, '--print']
            if ENABLE_DANGEROUS_PERMISSIONS:
                cmd.append('--dangerously-skip-permissions')
            
            # デバッグ: コマンドを表示
            print(f"[DEBUG] コマンド: {' '.join(cmd)} '{claude_prompt[:50]}...'")
            
            # セッションの作業ディレクトリを取得
            current_dir = session_directories.get(session_id, STARTUP_DIRECTORY)
            
            # 環境変数を設定してディレクトリコンテキストを強化
            env = os.environ.copy()
            env['CLAUDE_WORKING_DIR'] = current_dir
            env['PWD'] = current_dir
            
            result = subprocess.run(
                cmd + [claude_prompt],
                capture_output=True,
                text=True,
                timeout=CLAUDE_TIMEOUT,  # 設定値に基づくタイムアウト
                cwd=current_dir,
                env=env
            )
            
            print(f"[DEBUG] 戻りコード: {result.returncode}")
            print(f"[DEBUG] stdout長: {len(result.stdout) if result.stdout else 0}")
            print(f"[DEBUG] stderr長: {len(result.stderr) if result.stderr else 0}")
            
            if result.returncode == 0 and result.stdout:
                response = result.stdout.strip()
                return response
            elif result.stderr:
                # エラーメッセージを詳しく表示
                error_detail = result.stderr.strip()
                print(f"[ERROR] Claude Code stderr: {error_detail}")
                return f"⚠️ Claude Code エラー:\n{error_detail}"
            else:
                return "Claude Codeからの応答がありませんでした。"
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Claude Code タイムアウト")
            return "⏰ Claude Codeのレスポンスがタイムアウトしました（60秒）"
        except FileNotFoundError:
            print("[ERROR] Claude Code CLIが見つかりません")
            return "❌ エラー: Claude Code CLIが見つかりません。'claude'コマンドがPATHに含まれているか確認してください。"
        except Exception as e:
            import traceback
            print(f"[ERROR] Claude Code実行エラー: {str(e)}")
            print(traceback.format_exc())
            return f"❌ Claude Code実行エラー: {str(e)}"
    
    def is_markdown_related_request(self, message):
        """メッセージが.mdファイル関連かどうかをチェック"""
        import re
        
        # .mdファイルに関連するパターンをチェック
        md_patterns = [
            r'\.md\b',  # .md拡張子の直接言及
            r'README',  # READMEファイル
            r'REQUIREMENTS',  # REQUIREMENTSファイル
            r'CHANGELOG',  # CHANGELOGファイル
            r'マークダウン',  # マークダウン関連の日本語
            r'markdown',  # markdownの英語
        ]
        
        message_lower = message.lower()
        for pattern in md_patterns:
            if re.search(pattern, message_lower, re.IGNORECASE):
                return True
        
        return False
    
    def handle_directory_change(self):
        """ディレクトリ変更API"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            session_id = data.get('session_id', str(uuid.uuid4()))
            new_path = data.get('path', '')
            
            # セッション初期化
            if session_id not in session_directories:
                session_directories[session_id] = STARTUP_DIRECTORY
            
            current_dir = session_directories[session_id]
            
            if new_path:
                # 相対パスまたは絶対パスを処理
                if os.path.isabs(new_path):
                    target_path = new_path
                else:
                    target_path = os.path.join(current_dir, new_path)
                
                # パスを正規化
                target_path = os.path.abspath(target_path)
                
                # ディレクトリの存在確認と変更
                if os.path.isdir(target_path):
                    session_directories[session_id] = target_path
                    success = True
                    message = f"ディレクトリを '{target_path}' に変更しました"
                    print(f"[INFO] セッション {session_id[:8]} のディレクトリを変更: {target_path}")
                elif not os.path.exists(target_path):
                    # ディレクトリが存在しない場合は作成を試みる
                    try:
                        os.makedirs(target_path, exist_ok=True)
                        session_directories[session_id] = target_path
                        success = True
                        message = f"ディレクトリを作成して '{target_path}' に変更しました"
                        print(f"[INFO] セッション {session_id[:8]} のディレクトリを作成・変更: {target_path}")
                    except OSError as e:
                        success = False
                        message = f"ディレクトリの作成に失敗しました: {target_path} ({str(e)})"
                else:
                    success = False
                    message = f"指定されたパスはディレクトリではありません: {target_path}"
            else:
                success = False
                message = "パスが指定されていません"
            
            # レスポンス
            result = {
                "success": success,
                "message": message,
                "current_directory": session_directories[session_id],
                "session_id": session_id
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            error_msg = f"ディレクトリ変更エラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_msg}, ensure_ascii=False).encode('utf-8'))
    
    def handle_directory_info(self):
        """ディレクトリ情報取得API"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            session_id = data.get('session_id', str(uuid.uuid4()))
            
            print(f"[DEBUG] ディレクトリ情報要求 - セッション: {session_id[:8]}")
            print(f"[DEBUG] 現在のセッションディレクトリ: {session_directories}")
            
            # セッション初期化
            if session_id not in session_directories:
                session_directories[session_id] = STARTUP_DIRECTORY
                print(f"[DEBUG] セッション初期化: {session_id[:8]} -> {session_directories[session_id]}")
            
            current_dir = session_directories[session_id]
            print(f"[DEBUG] 使用するディレクトリ: {current_dir}")
            
            # ディレクトリ内容を取得
            try:
                items = []
                for item in os.listdir(current_dir):
                    item_path = os.path.join(current_dir, item)
                    is_dir = os.path.isdir(item_path)
                    items.append({
                        "name": item,
                        "is_directory": is_dir,
                        "path": item_path
                    })
                
                # ディレクトリを先頭に、ファイルを後に並べる
                items.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))
                
                result = {
                    "current_directory": current_dir,
                    "items": items,
                    "session_id": session_id
                }
                
            except PermissionError:
                result = {
                    "current_directory": current_dir,
                    "items": [],
                    "error": "ディレクトリへのアクセス権限がありません",
                    "session_id": session_id
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            error_msg = f"ディレクトリ情報取得エラー: {str(e)}"
            print(f"[ERROR] {error_msg}")
            
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
            self.end_headers()
            self.wfile.write(json.dumps({"error": error_msg}, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', CORS_ALLOW_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    
    def log_message(self, format, *args):
        """アクセスログをカスタマイズ"""
        # favicon.icoの404エラーを無視
        if len(args) > 0 and 'favicon.ico' in str(args):
            return
        # POSTリクエストのログは別途出力するので重複を避ける
        if len(args) > 0 and isinstance(args[0], str) and args[0].startswith('POST'):
            return
        super().log_message(format, *args)


def check_port_available(host, port):
    """ポートが使用可能かチェック"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # 0なら接続できた（ポート使用中）
    except Exception:
        return True  # エラーの場合は使用可能と判断

def main():
    """Main entry point for the package"""
    global PORT, HOST
    
    parser = argparse.ArgumentParser(
        description='Claude Code Chat Server - Multiple instances supported',
        epilog='''
Examples:
  %(prog)s                    # Start on default port 8081
  %(prog)s -p 8082           # Start on port 8082
  %(prog)s -p 8083 -H 0.0.0.0  # Start on port 8083, all interfaces
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--port', '-p', type=int, default=PORT, 
                        help=f'Port to run the server on (default: {PORT})')
    parser.add_argument('--host', '-H', default=HOST,
                        help=f'Host to bind the server to (default: {HOST})')
    parser.add_argument('--version', '-v', action='version', 
                        version=f'%(prog)s 1.0.0')
    
    args = parser.parse_args()
    
    # Override configuration with command line arguments
    PORT = args.port
    HOST = args.host
    
    # ポートが使用可能かチェック
    if not check_port_available(HOST, PORT):
        print(f"❌ Error: Port {PORT} is already in use on {HOST}")
        print(f"💡 Try a different port: {parser.prog} --port {PORT + 1}")
        return 1
    
    # インスタンス識別子を生成
    instance_id = f"PID{os.getpid()}"
    
    # ANSI color codes
    CYAN = '\033[96m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # ASCII art logo with colors
    print("\n" + f"{BLUE}{'=' * 80}{RESET}")
    print(f"""{BOLD}{CYAN}
  ██████╗  ██████╗     {GREEN}██╗    ██╗ ███████╗ ██████╗       {MAGENTA}██████╗ ██╗  ██╗  █████╗  ████████╗
 ██╔════╝ ██╔════╝     {GREEN}██║    ██║ ██╔════╝ ██╔══██╗     {MAGENTA}██╔════╝ ██║  ██║ ██╔══██╗ ╚══██╔══╝
 ██║      ██║          {GREEN}██║ █╗ ██║ █████╗   ██████╔╝     {MAGENTA}██║      ███████║ ███████║    ██║
 ██║      ██║          {GREEN}██║███╗██║ ██╔══╝   ██╔══██╗     {MAGENTA}██║      ██╔══██║ ██╔══██║    ██║
 ╚██████╗ ╚██████╗     {GREEN}╚███╔███╔╝ ███████╗ ██████╔╝     {MAGENTA}╚██████╗ ██║  ██║ ██║  ██║    ██║
  ╚═════╝  ╚═════╝      {GREEN}╚══╝╚══╝  ╚══════╝ ╚═════╝       {MAGENTA}╚═════╝ ╚═╝  ╚═╝ ╚═╝  ╚═╝    ╚═╝
{RESET}    """)
    print(f"{BLUE}{'=' * 80}{RESET}")
    
    # Get actual IP address
    try:
        hostname_result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
        if hostname_result.returncode == 0 and hostname_result.stdout.strip():
            # Get the first IP address from the output
            actual_ip = hostname_result.stdout.strip().split()[0]
        else:
            actual_ip = HOST
    except:
        actual_ip = HOST
    
    print(f"\n🚀 Claude Code Chat Server v1.0.0 [Instance: {instance_id}]")
    print(f"📍 URL: http://{actual_ip}:{PORT}/claude_chat.html")
    print(f"📁 Root Directory: {STARTUP_DIRECTORY}")
    print(f"🔧 Process ID: {os.getpid()}")
    print("=" * 80)
    print("💬 会話型インターフェース")
    print("🔧 デバッグモード有効")
    print(f"⏰ タイムアウト: {CLAUDE_TIMEOUT}秒")
    print("📦 Multiple instances supported")
    print("=" * 60)
    print(f"\n{instance_id} - 待機中 (Port: {PORT})...\n")
    
    # ポートの再利用を許可
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer((HOST, PORT), ClaudeChatHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 サーバーを停止します...")
    except Exception as e:
        print(f"\n❌ サーバーエラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
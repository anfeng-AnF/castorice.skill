"""
GPT-SoVITS TTS 脚本
用法:
    python ttsScript.py "要说的话"
    python ttsScript.py "要说的话" --lang 中文 --emotion 中立
    python ttsScript.py "要说的话" --ref "自定义参考音频路径"
    python ttsScript.py "要说的话" --port 9880 --mode api

流程:
    1. 上传参考音频至 Gradio 服务器（或直接调用 api_v2.py）
    2. 调用 TTS 接口生成语音
    3. 保存至 temp 目录
    4. 复制至 qqbot 媒体目录（用于发送）
"""

import os
import sys
import json
import shutil
import time
import argparse
import subprocess
import requests
import socket

# 强制 stdout 使用 UTF-8，避免 Windows GBK 编码问题
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
#  配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(SCRIPT_DIR, "temp")
QQB_MEDIA_DIR = os.path.join(
    os.path.expanduser("~"), ".openclaw", "media", "qqbot"
)

# 参考音频目录（相对于脚本所在目录）
SKILL_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
REF_AUDIO_BASE = os.path.join(SKILL_DIR, "reference_audios", "中文", "emotions")

# 情绪 → 参考音频文件名映射
EMOTION_MAP = {
    "中立": "【中立】这样的太阳…恐怕无法温暖来世的冥界。.wav",
    "吃惊": "【吃惊】这个…墨涅塔祭司手册里就是这么记载的…….wav",
    "开心": "【开心】作为助讲的风堇小姐…真是那刻夏老师的克星呀。.wav",
    "恐惧": "【恐惧】…就是这里了。.wav",
    "难过": "【难过】果然，「黑色」的「利剑」和「斗篷」…….wav",
}

# 情绪 → 参考文本映射
PROMPT_TEXT_MAP = {
    "中立": "这样的太阳…恐怕无法温暖来世的冥界。",
    "吃惊": "这个…墨涅塔祭司手册里就是这么记载的……",
    "开心": "作为助讲的风堇小姐…真是那刻夏老师的克星呀。",
    "恐惧": "…就是这里了。",
    "难过": "果然，「黑色」的「利剑」和「斗篷」……",
}

# ============================================================
#  GPT-SoVITS 进程管理
# ============================================================

# GPT-SoVITS 安装目录（优先级：CLI 参数 > 环境变量 > 自动探测）
def _detect_sovits_dir():
    """尝试自动探测 GPT-SoVITS 目录"""
    # 常见安装位置
    candidates = [
        os.path.join("F:\\", "Apps", "GPT-SoVITS-v2pro-20250604"),
        os.path.join(os.path.expanduser("~"), "GPT-SoVITS-v2pro-20250604"),
        os.path.join(os.path.expanduser("~"), "GPT-SoVITS"),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "runtime", "python.exe")):
            return c
    return None

GPT_SOVITS_DIR = os.environ.get("GPT_SOVITS_DIR") or _detect_sovits_dir()
GPT_SOVITS_PYTHON = os.path.join(GPT_SOVITS_DIR, "runtime", "python.exe") if GPT_SOVITS_DIR else None
GPT_SOVITS_WEBUI = os.path.join(GPT_SOVITS_DIR, "webui.py") if GPT_SOVITS_DIR else None


def is_port_open(host, port, timeout=2):
    """检查端口是否可连接"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError):
        return False


def ensure_server_running(host="127.0.0.1", port=9872, mode="api",
                          max_wait=180, sovits_dir=None):
    """确保 GPT-SoVITS 服务正在运行，未运行则自动启动

    mode="api"  → 启动 api_v2.py（轻量快速，仅提供 /tts 接口）
    mode="gradio" → 启动 webui.py（完整 WebUI，含可视化界面）
    """
    if is_port_open(host, port):
        print(f"[✓] GPT-SoVITS 服务已在 {host}:{port} 运行")
        return True

    print(f"[!] GPT-SoVITS 服务未运行，正在启动...")
    print(f"    目录: {GPT_SOVITS_DIR}")

    sovits_dir = sovits_dir or GPT_SOVITS_DIR
    if not sovits_dir or not os.path.exists(sovits_dir):
        print(f"[✗] 未找到 GPT-SoVITS 目录")
        print(f"    请通过 --sovits-dir 参数或 GPT_SOVITS_DIR 环境变量指定")
        return False

    python_exe = os.path.join(sovits_dir, "runtime", "python.exe")
    if not os.path.exists(python_exe):
        print(f"[✗] 未找到 Python 运行时: {python_exe}")
        return False

    # 根据模式选择启动方式
    if mode == "api":
        cmd = [python_exe, "-I", "api_v2.py",
               "-a", host, "-p", str(port)]
        print(f"    启动命令: api_v2.py -a {host} -p {port}")
    else:
        cmd = [python_exe, "-I", "webui.py", "zh_CN"]
        print(f"    启动命令: webui.py zh_CN")

    try:
        subprocess.Popen(
            cmd,
            cwd=sovits_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
    except Exception as e:
        print(f"[✗] 启动失败: {e}")
        return False

    # 等待服务就绪
    print(f"[⏳] 等待服务就绪（最长 {max_wait}s）...")
    start = time.time()
    while time.time() - start < max_wait:
        if is_port_open(host, port):
            elapsed = int(time.time() - start)
            print(f"[✓] 服务已就绪（耗时 {elapsed}s）")
            return True
        time.sleep(3)

    print(f"[✗] 等待超时，服务未能在 {max_wait}s 内就绪")
    return False


# 语言名 → API 语言代码映射
LANG_MAP = {
    "中文": "zh", "英文": "en", "日文": "ja", "粤语": "yue",
    "韩文": "ko", "中英混合": "zh", "日英混合": "ja",
    "粤英混合": "yue", "韩英混合": "ko",
    "多语种混合": "auto", "多语种混合(粤语)": "auto",
    "zh": "zh", "en": "en", "ja": "ja", "ko": "ko",
}


# 默认推理参数
DEFAULT_PARAMS = {
    "top_k": 15,
    "top_p": 1.0,
    "temperature": 1.0,
    "text_split_method": "cut5",
    "batch_size": 1,
    "batch_threshold": 0.75,
    "split_bucket": True,
    "speed_factor": 1.0,
    "fragment_interval": 0.3,
    "seed": -1,
    "parallel_infer": True,
    "repetition_penalty": 1.35,
    "sample_steps": 8,
    "super_sampling": False,
}


# ============================================================
#  Gradio 模式（当前 WebUI 运行方式）
# ============================================================

def tts_gradio(text, ref_audio_path, prompt_text, prompt_lang="中文",
               text_lang="中文", host="127.0.0.1", port=9872, **kwargs):
    """通过 Gradio WebUI 的 /call/get_tts_wav 接口生成语音"""
    base_url = f"http://{host}:{port}"

    # Step 1: 上传参考音频
    print(f"[1/4] 上传参考音频: {os.path.basename(ref_audio_path)}")
    with open(ref_audio_path, "rb") as f:
        upload_resp = requests.post(
            f"{base_url}/upload",
            files={"files": (os.path.basename(ref_audio_path), f, "audio/wav")},
            timeout=30,
        )
    upload_resp.raise_for_status()
    uploaded_path = upload_resp.json()[0]
    print(f"      服务器路径: {uploaded_path}")

    # Step 2: 调用 TTS
    print(f"[2/4] 调用 TTS 接口...")
    print(f"      文本: {text}")

    params = {**DEFAULT_PARAMS, **kwargs}

    payload = {
        "data": [
            {"path": uploaded_path, "meta": {"_type": "gradio.FileData"}},
            prompt_text,
            prompt_lang,
            text,
            text_lang,
            "凑四句一切",           # text_split_method 的 Gradio 内部值
            params["top_k"],
            params["top_p"],
            params["temperature"],
            params["split_bucket"],
            params["batch_size"],
            False,                  # 是否开启无参考文本模式
            None,                   # aux_ref_audio_paths
            params["sample_steps"],
            params["super_sampling"],
            params["fragment_interval"],
        ]
    }

    call_resp = requests.post(
        f"{base_url}/call/get_tts_wav", json=payload, timeout=30
    )
    call_resp.raise_for_status()
    event_id = call_resp.json()["event_id"]
    print(f"      event_id: {event_id}")

    # Step 3: 等待生成完成（SSE 流）
    print(f"[3/4] 等待语音生成...")
    sse_resp = requests.get(
        f"{base_url}/call/get_tts_wav/{event_id}", stream=True, timeout=300
    )
    sse_resp.raise_for_status()

    audio_path = None
    for line in sse_resp.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if decoded.startswith("event: generating"):
            print("      ⏳ 生成中...")
        elif decoded.startswith("event: complete"):
            # 下一行就是 data
            pass
        elif decoded.startswith("data:") and audio_path is None:
            data_str = decoded[5:].strip()
            result = json.loads(data_str)
            audio_path = result[0]["path"]
            print(f"      ✅ 生成完成")

    if not audio_path or not os.path.exists(audio_path):
        raise RuntimeError("TTS 生成失败，未返回有效音频路径")

    return audio_path


# ============================================================
#  FastAPI 模式（api_v2.py 独立运行时）
# ============================================================

def tts_api(text, ref_audio_path, prompt_text, prompt_lang="zh",
            text_lang="zh", host="127.0.0.1", port=9880, **kwargs):
    """通过 api_v2.py 的 /tts 接口直接生成语音"""
    base_url = f"http://{host}:{port}"

    params = {**DEFAULT_PARAMS, **kwargs}

    payload = {
        "text": text,
        "text_lang": text_lang,
        "ref_audio_path": ref_audio_path,
        "prompt_text": prompt_text,
        "prompt_lang": prompt_lang,
        "text_split_method": params["text_split_method"],
        "batch_size": params["batch_size"],
        "top_k": params["top_k"],
        "top_p": params["top_p"],
        "temperature": params["temperature"],
        "speed_factor": params["speed_factor"],
        "seed": params["seed"],
        "media_type": "wav",
        "streaming_mode": False,
    }

    print(f"[1/2] 调用 api_v2.py /tts 接口...")
    print(f"      文本: {text}")

    resp = requests.post(f"{base_url}/tts", json=payload, timeout=300)

    # 检查返回类型：成功时返回 wav 音频流，失败时返回 json 错误
    content_type = resp.headers.get("content-type", "")
    if resp.status_code != 200:
        try:
            err = resp.json()
            raise RuntimeError(f"TTS API 错误 ({resp.status_code}): {err}")
        except (ValueError, KeyError):
            raise RuntimeError(f"TTS API 错误 ({resp.status_code}): {resp.text[:200]}")

    if "json" in content_type:
        # 可能是错误响应
        err = resp.json()
        raise RuntimeError(f"TTS API 返回了 JSON 而非音频: {err}")

    # 保存到临时文件
    ts = int(time.time() * 1000)
    output_path = os.path.join(TEMP_DIR, f"tts_{ts}.wav")
    with open(output_path, "wb") as f:
        f.write(resp.content)

    print(f"[2/2] ✅ 生成完成 ({len(resp.content)} bytes)")
    return output_path


# ============================================================
#  主流程
# ============================================================

def run_tts(text, emotion="中立", ref_audio=None, prompt_text=None,
            mode="gradio", host="127.0.0.1", port=9872,
            text_lang="中文", prompt_lang="中文", sovits_dir=None, **kwargs):
    """
    完整 TTS 流程:
        1. 确定参考音频
        2. 调用 API 生成语音
        3. 保存至 temp/
        4. 复制至 qqbot 媒体目录
    """
    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(QQB_MEDIA_DIR, exist_ok=True)

    # --- 确保服务运行 ---
    if not ensure_server_running(host=host, port=port, mode=mode,
                                  sovits_dir=sovits_dir):
        raise RuntimeError(f"GPT-SoVITS 服务启动失败 (mode={mode})")

    # --- 确定参考音频 ---
    if ref_audio:
        ref_audio_path = ref_audio
    else:
        if emotion not in EMOTION_MAP:
            print(f"⚠️  未知情绪 '{emotion}'，回退到 '中立'")
            emotion = "中立"
        ref_audio_path = os.path.join(REF_AUDIO_BASE, EMOTION_MAP[emotion])

    if not os.path.exists(ref_audio_path):
        raise FileNotFoundError(f"参考音频不存在: {ref_audio_path}")

    if prompt_text is None:
        prompt_text = PROMPT_TEXT_MAP.get(emotion, "")

    # 语言名 → 代码
    text_lang_code = LANG_MAP.get(text_lang, text_lang)
    prompt_lang_code = LANG_MAP.get(prompt_lang, prompt_lang)

    print("=" * 50)
    print(f"  情绪: {emotion}")
    print(f"  文本: {text}")
    print(f"  模式: {mode}")
    print("=" * 50)

    # --- 调用 API ---
    if mode == "gradio":
        # Gradio WebUI 期望中文语言名
        server_audio_path = tts_gradio(
            text=text,
            ref_audio_path=ref_audio_path,
            prompt_text=prompt_text,
            prompt_lang=prompt_lang,
            text_lang=text_lang,
            host=host,
            port=port,
            **kwargs,
        )
        # 保存至 temp
        ts = int(time.time() * 1000)
        temp_path = os.path.join(TEMP_DIR, f"tts_{ts}.wav")
        shutil.copy2(server_audio_path, temp_path)
    else:
        # FastAPI 模式：已直接保存到 temp
        temp_path = tts_api(
            text=text,
            ref_audio_path=ref_audio_path,
            prompt_text=prompt_text,
            prompt_lang=prompt_lang_code,
            text_lang=text_lang_code,
            host=host,
            port=port,
            **kwargs,
        )

    # --- 复制至 qqbot 媒体目录 ---
    qqbot_path = os.path.join(QQB_MEDIA_DIR, "castorice_voice.wav")
    shutil.copy2(temp_path, qqbot_path)

    print(f"\n📁 已保存至: {temp_path}")
    print(f"📤 已复制至: {qqbot_path}")
    print(f"\n发送标签: <qqmedia>{qqbot_path}</qqmedia>")

    return qqbot_path


# ============================================================
#  CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="GPT-SoVITS TTS 脚本 — 遐蝶语音生成"
    )
    parser.add_argument("text", help="要合成的文本")
    parser.add_argument(
        "--emotion", "-e", default="中立",
        choices=list(EMOTION_MAP.keys()),
        help="情绪 (默认: 中立)"
    )
    parser.add_argument("--ref", default=None, help="自定义参考音频路径")
    parser.add_argument("--prompt-text", default=None, help="参考音频的文本内容")
    parser.add_argument(
        "--mode", "-m", default="api", choices=["gradio", "api"],
        help="调用模式: api(默认,api_v2.py) 或 gradio(WebUI)"
    )
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", "-p", type=int, default=9872, help="端口号")
    parser.add_argument("--text-lang", default="中文", help="合成文本语种")
    parser.add_argument("--prompt-lang", default="中文", help="参考音频语种")
    parser.add_argument("--speed", type=float, default=1.0, help="语速因子")
    parser.add_argument("--top-k", type=int, default=15, help="top_k 采样")
    parser.add_argument("--temperature", type=float, default=1.0, help="温度")
    parser.add_argument("--seed", type=int, default=-1, help="随机种子 (-1=随机)")
    parser.add_argument("--sovits-dir", default=None,
                        help="GPT-SoVITS 安装目录 (也可通过 GPT_SOVITS_DIR 环境变量设置)")

    args = parser.parse_args()

    extra = {}
    if args.speed != 1.0:
        extra["speed_factor"] = args.speed
    if args.top_k != 15:
        extra["top_k"] = args.top_k
    if args.temperature != 1.0:
        extra["temperature"] = args.temperature
    if args.seed != -1:
        extra["seed"] = args.seed

    try:
        path = run_tts(
            text=args.text,
            emotion=args.emotion,
            ref_audio=args.ref,
            prompt_text=args.prompt_text,
            mode=args.mode,
            host=args.host,
            port=args.port,
            text_lang=args.text_lang,
            prompt_lang=args.prompt_lang,
            sovits_dir=args.sovits_dir,
            **extra,
        )
        print(f"\n✅ 完成")
    except Exception as e:
        print(f"\n❌ 失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

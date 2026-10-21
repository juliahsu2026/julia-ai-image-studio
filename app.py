import base64
import io
import os
import warnings

import requests
import streamlit as st
from dotenv import load_dotenv
from PIL import Image, ImageOps
from runwayml import RunwayML

load_dotenv()

st.set_page_config(page_title="圖片生成影片", page_icon="🎬")
st.title("🎬 圖片生成影片")
st.caption("上傳一張圖片，描述想要的動作、鏡頭與氛圍。")

api_key = os.getenv("RUNWAYML_API_SECRET")
if not api_key:
    try:
        api_key = st.secrets["RUNWAYML_API_SECRET"]
    except (FileNotFoundError, KeyError):
        api_key = None

if not api_key:
    st.error("請先在 .env 設定 RUNWAYML_API_SECRET，然後重新啟動。")
    st.stop()

# 停用建立任務的自動重試，避免不確定結果時重複送出。
client = RunwayML(api_key=api_key, timeout=30, max_retries=0)

for key, default in {
    "task_id": None,
    "finished": False,
    "video_url": None,
    "video_bytes": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

busy = bool(st.session_state.task_id) and not st.session_state.finished


def prepare_image(upload, size):
    if upload.size > 10 * 1024 * 1024:
        raise ValueError("圖片不能超過 10 MB。")

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        image = Image.open(upload)
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")

    # 裁切至影片比例，避免上游服務自行決定裁切方式。
    image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return image, "data:image/jpeg;base64," + encoded


with st.form("generation"):
    upload = st.file_uploader(
        "上傳圖片",
        type=["jpg", "jpeg", "png", "webp"],
        disabled=busy,
    )
    prompt = st.text_area(
        "內容指令",
        placeholder="例如：讓照片中的花朵隨風輕輕搖曳，鏡頭緩慢推近，"
                    "保持原本的色彩與柔和光線。",
        max_chars=1000,
        disabled=busy,
    )
    col1, col2 = st.columns(2)
    ratio_label = col1.selectbox(
        "影片比例",
        ["橫式 16:9", "直式 9:16"],
        disabled=busy,
    )
    duration = col2.selectbox(
        "影片秒數",
        [5, 10],
        disabled=busy,
    )
    st.caption("按下生成後，圖片與指令會傳送至 Runway，並使用帳戶額度。")
    submitted = st.form_submit_button(
        "開始生成影片",
        type="primary",
        disabled=busy,
    )

if submitted:
    if upload is None or not prompt.strip():
        st.warning("請上傳圖片並填寫內容指令。")
    else:
        size = (
            (1280, 720)
            if ratio_label == "橫式 16:9"
            else (720, 1280)
        )
        try:
            preview, image_uri = prepare_image(upload, size)
            st.image(
                preview,
                caption="送出的圖片（已依影片比例裁切）",
            )
            with st.spinner("正在送出生成任務…"):
                task = client.image_to_video.create(
                    model="gen4_turbo",
                    prompt_image=image_uri,
                    prompt_text=prompt.strip(),
                    ratio=f"{size[0]}:{size[1]}",
                    duration=duration,
                )
            st.session_state.update(
                task_id=task.id,
                finished=False,
                video_url=None,
                video_bytes=None,
            )
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error(
                "無法送出任務，請檢查圖片、API 金鑰、帳戶額度與網路。"
                "若發生連線逾時，請先至 Runway 後台確認是否已建立任務，"
                "以免重複付費。"
            )


@st.fragment(run_every="10s")
def task_panel():
    task_id = st.session_state.task_id
    if not task_id:
        return

    st.caption(f"任務編號：{task_id}")

    if not st.session_state.finished:
        try:
            task = client.tasks.retrieve(task_id)
        except Exception:
            st.warning("暫時無法查詢狀態，稍後會自動重試。")
            return

        status = task.status
        if status == "SUCCEEDED":
            outputs = getattr(task, "output", None) or []
            st.session_state.finished = True
            if outputs:
                st.session_state.video_url = outputs[0]
            else:
                st.error("任務已結束，但服務未回傳影片。")
            st.rerun()
        elif status in ("FAILED", "CANCELED", "CANCELLED"):
            st.session_state.finished = True
            st.error("生成失敗或已取消。請至 Runway 後台查看原因。")
            st.rerun()
        else:
            st.info(
                f"影片處理中：{status}，每 10 秒自動更新。"
            )
            st.caption("等待期間請保持此頁開啟。")
            return

    url = st.session_state.video_url
    if not url:
        st.warning("此任務沒有可播放的影片，可重新送出生成。")
        return

    st.success("影片生成完成！")
    st.video(url)

    if st.session_state.video_bytes is None:
        if st.button("準備下載 MP4"):
            try:
                with st.spinner("正在下載影片…"):
                    with requests.get(
                        url,
                        timeout=(10, 120),
                        stream=True,
                    ) as response:
                        response.raise_for_status()
                        data = bytearray()
                        for chunk in response.iter_content(1024 * 1024):
                            data.extend(chunk)
                            if len(data) > 200 * 1024 * 1024:
                                raise ValueError("影片超過 200 MB。")
                st.session_state.video_bytes = bytes(data)
                st.rerun()
            except Exception:
                st.error(
                    "下載失敗，請稍後重試；影片連結也可能已過期。"
                )
    else:
        st.download_button(
            "下載 MP4 影片",
            data=st.session_state.video_bytes,
            file_name=f"video-{task_id}.mp4",
            mime="video/mp4",
        )


task_panel()

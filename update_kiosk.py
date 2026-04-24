import asyncio
import os
import re
import threading
import time
from dotenv import load_dotenv

from livekit import agents
from livekit.agents import JobContext, WorkerOptions, cli, llm
from livekit.agents.voice import AgentSession, Agent
from livekit.plugins import deepgram, silero, cartesia


from virtual_staff_brain_3_0 import (
    process_patient_query,
    fetch_patient_record,
    reset_brain_memory,
    quick_route,
)

# ====================================================================
# [0] LỚP BẢO VỆ GIỌNG NÓI (VOICE SAFETY LAYER - CHUẨN TIẾNG VIỆT)
# ====================================================================

FALLBACK_RESPONSE = "Dạ, hệ thống đang gặp chút sự cố. Cô chú vui lòng đợi một lát ạ."

def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    return text

def normalize_for_tts(text: str) -> str:
    if not text:
        return ""
    text = strip_markdown(text)
    
    # Chỉ xóa bỏ dấu ngoặc, GIỮ NGUYÊN chữ bên trong (chống lỗi Cartesia câm)
    text = re.sub(r'([.,!?])([a-zA-ZÀ-ỹ])', r'\1 \2', text)
    text =text.lower()
    text = text.replace("[", "").replace("]", "")
    text = text.replace("/", " hoặc ")
    
    # Giữ lại chữ cái (bao gồm cả tiếng Việt có dấu), số và dấu câu cơ bản
    text = re.sub(r'[^\w\s.,!?\'-ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơƯĂẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂẾỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸửữựýỵỷỹ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def ensure_tts_safe(text: str) -> str:
    text = normalize_for_tts(text)
    if len(text) < 3:
        return "Dạ cô chú nói lại giúp cháu được không ạ?"
    if not re.search(r'[a-zA-Z0-9À-ỹ]', text):
        return "Dạ cháu chưa nghe rõ, cô chú vui lòng nhắc lại ạ."
    if len(text) > 500:
        text = text[:497] + "..."
    return text

def humanize(text: str) -> str:
    text = text.strip()
    if not text:
        return "Dạ cô chú vui lòng chờ một lát."
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text

def smart_split(text: str, max_len: int = 150):
    if not text or len(text.strip()) == 0:
        return [FALLBACK_RESPONSE]
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return [text[:max_len]]

    chunks = []
    current = ""

    for s in sentences:
        if len(current) + len(s) + 1 < max_len:
            current += (" " + s if current else s)
        else:
            if current.strip():
                chunks.append(current.strip())
            current = s

    if current.strip():
        chunks.append(current.strip())

    if not chunks:
        chunks = [text[:max_len]]

    return chunks

# ====================================================================
# [1] LLM STREAM (TƯƠNG THÍCH TUYỆT ĐỐI LIVEKIT v1.5.2+)
# ====================================================================

class KioskBrainStream(llm.LLMStream):
    # CHÚ Ý: Đã thêm tham số is_duplicate
    def __init__(self, user_text, record_text, llm_instance, chat_ctx, conn_options=None, tools=None, is_duplicate=False):
        super().__init__(
            llm=llm_instance, 
            chat_ctx=chat_ctx, 
            conn_options=conn_options, 
            tools=tools,
        )
        self.user_text = user_text
        self.record_text = record_text
        self.llm_instance = llm_instance
        self.is_duplicate = is_duplicate
        self._queue = asyncio.Queue(maxsize=20)
        self._started = False
        self._run_called = False

    async def _run(self):
        if getattr(self, '_run_called', False):
            return
        self._run_called = True

        sid = id(self) % 10000  # ID ngắn để nhận biết luồng xử lý
        print(f"[RUN-{sid}] BẮT ĐẦU: trùng_lặp={self.is_duplicate} nội_dung='{self.user_text[:30]}'")
        try:
            if self.is_duplicate:
                print(f"[RUN-{sid}] THOÁT: Phát hiện luồng trùng lặp (is_duplicate=True)")
                await self._queue.put(None)
                return

            if not self.user_text.strip():
                fallback = humanize(ensure_tts_safe("Dạ cháu nghe chưa rõ, cô chú lặp lại giúp cháu với ạ."))
                await self._queue.put(fallback)
                return

            _fast = quick_route(self.user_text)

            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        process_patient_query,
                        self.user_text,
                        self.record_text,
                    ),
                    timeout=360,
                )
            except asyncio.TimeoutError:
                print(f"[RUN-{sid}] LỖI: Hết thời gian chờ (Timeout)")
                response = FALLBACK_RESPONSE
            except asyncio.CancelledError:
                print(f"[RUN-{sid}] HỦY: Tiến trình bị hủy trong lúc xử lý LLM!")
                raise

            print(f"[RUN-{sid}] Kết quả trả về='{(response or '')[:60]}'")

            if not response or not response.strip():
                print(f"[RUN-{sid}] THOÁT: Không có nội dung trả về")
                return

            chunks = smart_split(response)
            print(f"[RUN-{sid}] Chia thành {len(chunks)} đoạn: {[c[:25] for c in chunks]}")
            valid_chunks = []

            for chunk in chunks:
                safe = ensure_tts_safe(chunk)
                safe = humanize(safe)
                if safe and len(safe.strip()) > 3:
                    valid_chunks.append(safe)

            if not valid_chunks:
                fallback = humanize(ensure_tts_safe(FALLBACK_RESPONSE))
                valid_chunks = [fallback]
                print(f"[RUN-{sid}] CẢNH BÁO: Phải dùng câu trả lời dự phòng (fallback)")

            for chunk in valid_chunks:
                print(f"[RUN-{sid}] Đưa vào hàng đợi phát âm: '{chunk[:40]}'")
                await self._queue.put(chunk)

        except asyncio.CancelledError:
            print(f"[RUN-{sid}] HỦY: Tiến trình bị hủy (vòng ngoài)!")
            raise
        except Exception as e:
            print(f"[RUN-{sid}] LỖI HỆ THỐNG: {e}")
            fallback = humanize(ensure_tts_safe(FALLBACK_RESPONSE))
            await self._queue.put(fallback)

        finally:
            print(f"[RUN-{sid}] HOÀN TẤT → Kết thúc hàng đợi")
            await self._queue.put(None)
            if not self.is_duplicate:
                self.llm_instance.mark_done()

    async def __anext__(self) -> llm.ChatChunk:
        if not self._started:
            self._started = True
            asyncio.create_task(self._run())

        chunk = await self._queue.get()

        if chunk is None:
            raise StopAsyncIteration

        return llm.ChatChunk(
            id="kiosk-response",
            delta=llm.ChoiceDelta(role="assistant", content=chunk),
        )

class KioskBrainLLM(llm.LLM):
    def __init__(self):
        super().__init__()
        self.record_text = ""
        self.last_processed_text = ""
        self.last_call_time = 0
        self._dedup_lock = threading.Lock()
        self._is_processing = False  # Cờ đang xử lý request

    def mark_done(self):
        """Gọi khi _run() hoàn thành — refresh cooldown từ lúc response được giao."""
        with self._dedup_lock:
            self._is_processing = False
            self.last_call_time = time.time()  # Cửa sổ 20s bắt đầu lại từ đây

    def set_record_context(self, text):
        self.record_text = text

    def chat(self, chat_ctx: llm.ChatContext, conn_options=None, tools=None, *args, **kwargs) -> llm.LLMStream:
        msgs = (
            chat_ctx.messages()
            if callable(getattr(chat_ctx, "messages", None))
            else chat_ctx.messages
        )

        # Tìm tin nhắn NGƯỜI DÙNG cuối cùng (role=user)
        user_msg = ""
        for msg in reversed(msgs):
            if getattr(msg, "role", None) == "user":
                user_msg = msg.content
                break
        if not user_msg:
            user_msg = msgs[-1].content if msgs else ""

        if isinstance(user_msg, list):
            user_text = " ".join([getattr(m, "text", str(m)) for m in user_msg])
        else:
            user_text = str(user_msg)

        cleaned_text = re.sub(r'[^\w\s]', '', user_text).strip().lower()
        current_time = time.time()
        is_dup = False

        # DEBUG: hiển thị mọi lần chat() được gọi để phát hiện lần gọi thừa
        elapsed_now = current_time - self.last_call_time
        print(f"[CHAT] t+{elapsed_now:.1f}s | last='{self.last_processed_text[:30]}' | new='{cleaned_text[:30]}' | processing={self._is_processing}")

        with self._dedup_lock:
            SAME_COOLDOWN = 20  # Chặn cùng câu hỏi trong 20s kể từ lúc bắt đầu xử lý
            elapsed = current_time - self.last_call_time

            same_recently = (
                cleaned_text == self.last_processed_text
                and cleaned_text != ""
                and elapsed < SAME_COOLDOWN
            )
            too_fast = (elapsed < 2.0)

            if same_recently:
                is_dup = True
                print(f"[BỘ LỌC] Chặn xử lý trùng nội dung sau {elapsed:.1f}s: '{user_text[:50]}'")
            elif too_fast:
                is_dup = True
                print(f"[BỘ LỌC] Chặn dội âm (Echo) {elapsed:.2f}s: '{user_text[:50]}'")
            else:
                self.last_processed_text = cleaned_text
                self.last_call_time = current_time
                self._is_processing = True

        return KioskBrainStream(
            user_text=user_text,
            record_text=self.record_text,
            llm_instance=self,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
            is_duplicate=is_dup
        )
# ====================================================================
# [2] MAIN
# ====================================================================

async def entrypoint(ctx: JobContext):
    print("Starting kiosk...")

    # Kích hoạt Qdrant trên luồng xử lý chính thức để tránh xung đột Permission
    from virtual_staff_brain_3_0 import setup_qdrant
    setup_qdrant()

    await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)

    reset_brain_memory()
    #record = fetch_patient_record("bn-001")
    
    patient_id = "bn-008"


    # Phao cứu sinh: Nếu quên nhập hoặc lỗi, tự động xài BN-001

    
    record = fetch_patient_record(patient_id)
    
    print(f"[KHOI DONG] Ho so benh nhan [{patient_id}]:")
    print("-" * 40)
    print(record.strip())
    print("-" * 40)

    llm_instance = KioskBrainLLM()
    llm_instance.set_record_context(record)

    # Khởi tạo STT bằng Deepgram (Tai thính nhất)
    stt = deepgram.STT(language="vi", model="nova-2")
    vad = silero.VAD.load()
    
    # Khởi tạo TTS bằng Cartesia (Miệng nhanh nhất)
    # Lưu ý: model="sonic-3" là bắt buộc đối với Cartesia hiện tại
    tts = cartesia.TTS(model="sonic-3", language="vi", voice="b8cd71e3-bc14-4538-a530-d6314731c036")

    session = AgentSession(vad=vad, stt=stt, llm=llm_instance, tts=tts, turn_handling={
            "interruption": {
                "enabled": True,
            }
        }
    )

    agent = Agent(
        instructions=(
            "Bạn là Lễ tân bệnh viện.\n"
            "- Yêu cầu bệnh nhân nhâp ID hoặc thông tin để tra cứu hồ sơ\n"
            "- Nói rõ ràng và tự nhiên\n"
            "- Trả lời ngắn gọn (3-5 câu)\n"
            "- Lịch sự và bình tĩnh\n"
            "- Hướng dẫn rõ ràng\n"
        )
    )
    
    @session.on("user_started_speaking")
    def on_start():
        pass  # Im lặng — log sẽ xuất hiện khi có phản hồi hoàn chỉnh
    
    @session.on("user_speech_committed")
    def on_speech_committed(msg):
        print(f"\n[STT] {msg.content}")

    print("[HE THONG SAN SANG]")
    await session.start(room=ctx.room, agent=agent)

def prewarm(proc):
    print("Prewarming system...")

def main():
    load_dotenv()

    required = [
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "LIVEKIT_URL",
        "DEEPGRAM_API_KEY",
        "CARTESIA_API_KEY",
    ]

    missing = [k for k in required if not os.getenv(k)]

    if missing:
        print("Missing environment variables:", missing)
        exit(1)

    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        )
    )

if __name__ == "__main__":
    main()
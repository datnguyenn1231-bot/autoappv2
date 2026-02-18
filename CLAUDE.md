# AuraSplit v2 — AI Assistant Rules

> **MỌI AI assistant (Antigravity, Claude CLI, AI Studio, Grok) PHẢI đọc file này TRƯỚC KHI CODE.**

## 📋 Quy trình BẮT BUỘC

### Trước khi code:
1. Đọc `PROGRESS.md` → biết đang ở bước nào
2. Đọc `BRIEFING.md` → biết plan tổng thể
3. Xác nhận module nào đang làm → KHÔNG đụng module khác

### Sau khi code:
1. Test `npm run dev` → confirm app chạy OK
2. Update `PROGRESS.md` → đánh dấu ✅ bước vừa xong
3. Ghi lại file nào đã thay đổi + số dòng

### Khi chuyển module:
1. Verify module cũ hoạt động → test riêng
2. Commit (hoặc backup) trước khi sang module mới
3. KHÔNG sửa module cũ khi đang làm module mới

---

## 🔒 Quy tắc TUYỆT ĐỐI

| # | Rule | Lý do |
|:-:|------|-------|
| 1 | **Max 300 dòng/file** | AI context limit |
| 2 | **1 module 1 lúc** | Tránh fix A hỏng B |
| 3 | **Test sau mỗi thay đổi** | Phát hiện bug sớm |
| 4 | **Update PROGRESS.md** | Để AI tiếp theo biết |
| 5 | **Renderer KHÔNG import fs** | Security, IPC only |
| 6 | **TypeScript bắt buộc** | Type safety |
| 7 | **Windows ONLY** | Không cross-platform |

---

## 📁 Module Map — Thứ tự build

```
Module 1: Shell         ✅ DONE  — sidebar, views, router
Module 2: AI Cut        ⬜ NEXT  — SK1 + SK3, Python IPC
Module 3: Editor        ⬜       — Timeline, preview, cut/merge
Module 4: TTS           ⬜       — EdgeTTS, providers
Module 5: Download      ⬜       — yt-dlp IPC
Module 6: Metadata      ⬜       — SK6 FFmpeg strip
Module 7: Settings      ⬜       — Config, about
Module 8: License       ⬜ LAST  — Supabase, HWID
Module 9: Polish        ⬜       — Animations, installer
```

> ⚠️ **KHÔNG skip ahead.** Xong Module N rồi mới làm Module N+1.
> ⚠️ **KHÔNG quay lại sửa module cũ** trừ khi có bug critical.

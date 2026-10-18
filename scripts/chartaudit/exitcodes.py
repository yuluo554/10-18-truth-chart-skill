"""退出码契约（唯一语义，口径 data/README.md §15）。

0 = 审计通过且产物写出
1 = 审计完成但存在 ERROR（阻断发布；默认不写可发布 HTML）
2 = 用法 / 输入 / 规格错误
3 = 规则包 / 配置缺失 / 校验失败
"""

EXIT_OK = 0
EXIT_AUDIT_ERRORS = 1
EXIT_USAGE = 2
EXIT_CONFIG = 3


def ensure_utf8_stdio():
    """编码守卫：按 stream.encoding 探针决定是否 reconfigure（中文控制台 cp936 不动）。

    防 CI/子进程 cp1252 通道上的 UnicodeEncodeError（skill 纪律：本机 -X utf8 掩盖的盲区）。
    """
    import sys

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        enc = getattr(stream, "encoding", None)
        if enc and enc.lower().replace("-", "") not in ("utf8", "utf8mb4"):
            try:
                reconfigure = getattr(stream, "reconfigure", None)
                if reconfigure is not None:
                    reconfigure(encoding="utf-8")
            except (ValueError, OSError, AttributeError):
                # 兜底：无法 reconfigure 时保持原样（测试桩等非真实流）
                pass

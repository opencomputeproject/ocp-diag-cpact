import sys
import traceback
import datetime
import linecache


class CustomExceptionHandler:
    @staticmethod
    def format_exception(exc: Exception) -> str:
        tb = exc.__traceback__
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        exc_type = type(exc).__name__
        exc_msg = str(exc)

        lines = []
        lines.append("═" * 100)
        lines.append("💥  APPLICATION CRASHED")
        lines.append(f"🕒  Time      : {timestamp}")
        lines.append(f"❗  Type      : {exc_type}")
        lines.append(f"📄  Message   : {exc_msg}")
        lines.append("")
        lines.append("📌  Stack Trace:")
        lines.append("")

        for frame in traceback.extract_tb(tb):
            filename = frame.filename
            lineno = frame.lineno
            func = frame.name
            code = linecache.getline(filename, lineno).strip()

            lines.append(f"  ➤ File: {filename}")
            lines.append(f"    Line: {lineno}")
            lines.append(f"    Func: {func}")
            if code:
                lines.append(f"    Code: {code}")
            lines.append("")

        lines.append("🧨  Full Traceback:")
        lines.append("")

        full_tb = "".join(traceback.format_exception(type(exc), exc, tb))
        lines.append(full_tb)

        lines.append("═" * 100)

        return "\n".join(lines)

    @staticmethod
    def print_exception(exc: Exception):
        print(CustomExceptionHandler.format_exception(exc), file=sys.stderr)

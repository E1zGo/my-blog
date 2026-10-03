"""Render one original PDF page locally, without relying on a browser PDF plugin."""
import io
import math
from contextlib import closing
from threading import Lock

import pypdfium2 as pdfium

# PDFium calls must not overlap, including calls from different app instances.
_render_lock = Lock()


def render_page(path, number, width=1200):
    with _render_lock:
        try:
            with pdfium.PdfDocument(str(path)) as document:
                if not 1 <= number <= len(document):
                    raise ValueError("页码超出原文件范围。")
                with closing(document.get_page(number - 1)) as page:
                    page_width, page_height = page.get_size()
                    if not all(math.isfinite(v) and v > 0 for v in (page_width, page_height)):
                        raise ValueError("PDF 页面尺寸无效。")
                    # Bound both dimensions, including unusually tall/wide pages.
                    scale = min(width / page_width, 2400 / max(page_width, page_height))
                    with closing(page.render(scale=scale)) as bitmap:
                        with bitmap.to_pil() as image:
                            output = io.BytesIO()
                            image.save(output, format="PNG")
                            return output.getvalue()
        except pdfium.PdfiumError:
            raise ValueError("PDF 原文预览失败，请下载原文件使用本机阅读器打开。") from None

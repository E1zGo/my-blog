import re

RULES = [
    (r"CUDA out of memory|OutOfMemoryError", "GPU 显存不足", "日志中检测到显存分配失败。",
     "先记录 GPU 型号、可用显存和 batch size；关闭无关 GPU 进程，减小 batch size/输入分辨率，再验证是否仍复现。混合精度需确认模型支持。"),
    (r"ModuleNotFoundError: No module named ['\"]([^'\"]+)", "Python 依赖缺失", "当前解释器无法导入模块。",
     "先核对启动命令所用 Python 与虚拟环境是否一致，再检查仓库依赖清单。模块名不一定等于 PyPI 包名，不要盲目安装同名包。"),
    (r"FileNotFoundError|No such file or directory", "文件路径不存在", "程序访问的文件在当前路径下不存在。",
     "核对工作目录、配置中的相对路径、数据集和权重文件是否已准备好；优先按 README 的目录要求检查。"),
    (r"size mismatch|shapes cannot be multiplied|must match the size", "张量或权重维度不匹配", "检测到形状不匹配的报错。",
     "检查模型配置与权重版本、类别数、输入尺寸；记录出错张量 shape，不要直接忽略 strict 加载错误。"),
    (r"CUDA.*(?:not available|driver|version)|not compiled with CUDA", "CUDA 环境可能不匹配", "日志包含 CUDA 可用性或版本错误。",
     "对照仓库依赖收集 Python、PyTorch、驱动和 CUDA 信息，再判断是 CPU 构建还是驱动兼容问题。不要仅按本机 toolkit 版本推断。"),
]


def diagnose(text):
    findings = []
    for pattern, title, reason, advice in RULES:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            findings.append({"title": title, "matched": match.group(0)[:220], "reason": reason,
                             "advice": advice, "certainty": "规则匹配的候选原因，尚未实际验证"})
    return findings

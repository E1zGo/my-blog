"""Auditable Chinese scientific query expansion, with no model or network."""
import re

# Phrases are alternatives, not an asserted translation of an entire question.
TERMS = {
    "主要内容": ["Abstract", "Introduction"], "讲了什么": ["Abstract", "Introduction"],
    "研究内容": ["Abstract", "Introduction"], "创新点": ["contributions"],
    "方法": ["method", "approach"], "原理": ["method", "approach"],
    "去噪": ["denoising"], "结论": ["conclusion", "conclusions"],
    "低光照图像增强": ["low-light enhancement"], "低光图像增强": ["low-light enhancement"],
    "低照度图像增强": ["low-light enhancement"], "扩散过程": ["diffusion process"],
    "退化": ["degradation"], "先验": ["prior"], "梯度": ["gradient"],
    "采样": ["sampling"], "消融": ["ablation"], "亮度": ["brightness"],
    "低光增强": ["low-light enhancement"], "低光照增强": ["low-light enhancement"],
    "低照度增强": ["low-light enhancement"], "暗光增强": ["low-light enhancement"],
    "图像恢复": ["image restoration", "image recovery"], "图像复原": ["image restoration", "image recovery"],
    "图像增强": ["image enhancement"], "生成式扩散先验": ["generative diffusion prior"],
    "扩散先验": ["diffusion prior"], "扩散模型": ["diffusion model", "diffusion models", "DDPM"],
    "去噪扩散": ["denoising diffusion", "DDPM"], "退化模型": ["degradation model"],
    "退化参数": ["degradation parameters"], "盲图像恢复": ["blind image restoration"],
    "盲恢复": ["blind image restoration"], "盲复原": ["blind image restoration"],
    "非线性": ["non-linear", "nonlinear"], "线性逆问题": ["linear inverse problems"],
    "分层引导": ["hierarchical guidance"], "层次引导": ["hierarchical guidance"],
    "多重引导": ["multiple guidance"], "多图像引导": ["multiple image guidance"],
    "单图像引导": ["single image guidance"], "条件引导": ["conditional guidance"],
    "任意分辨率": ["arbitrary resolutions", "arbitrary size"], "任意尺寸": ["arbitrary size", "arbitrary resolutions"],
    "图像分块": ["patch-based"], "超分辨率": ["super-resolution"], "去模糊": ["deblurring"],
    "图像修复": ["inpainting", "image restoration"], "图像补全": ["inpainting"],
    "图像上色": ["colorization"], "高动态范围": ["HDR", "high dynamic range"],
    "反向过程": ["reverse process"], "前向过程": ["forward process", "diffusion process"],
    "采样过程": ["sampling process"], "噪声预测": ["noise prediction", "predict noise"],
    "高斯噪声": ["Gaussian noise"], "损失函数": ["loss function", "loss"],
    "训练目标": ["training objective", "loss"], "无监督": ["unsupervised"],
    "有监督": ["supervised"], "零样本": ["zero-shot"], "预训练": ["pre-trained", "pretrained"],
    "消融实验": ["ablation study", "ablation"], "评估指标": ["evaluation metrics", "PSNR", "SSIM", "FID"],
    "峰值信噪比": ["PSNR"], "结构相似度": ["SSIM"], "数据集": ["dataset", "datasets"],
    "实验设置": ["experimental settings", "implementation details"], "实验结果": ["experimental results", "results"],
    "局限性": ["limitations"], "局限": ["limitations"], "贡献": ["contributions"],
    "注意力机制": ["attention mechanism", "attention"], "图像分割": ["image segmentation"],
    "语义分割": ["semantic segmentation"], "目标检测": ["object detection"],
    "学习率": ["learning rate"], "批大小": ["batch size"], "优化器": ["optimizer"],
    "模型权重": ["model weights", "checkpoint"], "环境依赖": ["requirements", "dependencies"],
}


def expand_query(query):
    remaining = query
    matches = []
    # Longest match first prevents e.g. supervised from matching unsupervised.
    for term in sorted(TERMS, key=len, reverse=True):
        if term in remaining:
            matches.append({"term": term, "alternatives": TERMS[term]})
            remaining = remaining.replace(term, " " * len(term))
    # "公式 8" can locate the equation number, without guessing its content.
    equation = re.search(r"公式\s*[（(]?\s*(\d{1,3})", query)
    if equation:
        matches.append({"term": equation.group(), "alternatives": ["(" + equation[1] + ")"]})
    return matches

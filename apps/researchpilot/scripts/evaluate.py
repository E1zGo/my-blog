"""Deterministic retrieval evaluation. No model credentials or outbound traffic."""
import json
from pathlib import Path
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from researchpilot.config import Settings
from researchpilot.db import Database, now
from researchpilot.library import Library


def main():
    fixture = json.loads((ROOT / "examples/demo.json").read_text(encoding="utf-8"))
    questions = json.loads((ROOT / "evals/questions.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(data_dir=Path(directory))
        db = Database(settings.data_dir)
        db.execute("INSERT INTO workspaces VALUES ('eval','evaluation',?)", (now(),))
        library = Library(db, settings)
        library.ingest("eval", "TinyRestore · 示例论文", "paper", list(enumerate(fixture["paper"], 1)))
        for name, text in fixture["files"].items():
            library.ingest("eval",name,"repository",[(None,text)])
        library.ingest("eval","example-error.log","log",[(None,fixture["log"])])
        rows, recalls, reciprocals, latencies, negative = [], [], [], [], []
        for item in questions:
            start = time.perf_counter()
            found = library.search("eval",item["query"],k=3)
            latency = (time.perf_counter() - start)*1000
            latencies.append(latency)
            expected = {(e["name"], e["page"]) for e in item["expected"]}
            retrieved = [(e["name"],e["page"]) for e in found]
            recall = len(expected & set(retrieved))/len(expected) if expected else None
            rr = next((1/(rank+1) for rank, pair in enumerate(retrieved) if pair in expected),0) if expected else None
            if expected:
                recalls.append(recall)
                reciprocals.append(rr)
            else:
                negative.append(not found)
            rows.append({**item,"retrieved":[{"name":a,"page":b} for a,b in retrieved],"recall_at_3":recall,"reciprocal_rank":rr,"elapsed_ms":round(latency,3)})
    result = {"generated_at":datetime.now(timezone.utc).isoformat(),"corpus":"TinyRestore synthetic teaching fixture v1",
              "retrieval":"BM25 with Chinese-English scientific term expansion","k":3,"questions":len(rows),
              "answerable_questions":len(recalls),"unanswerable_questions":len(negative),
              "recall_at_3":round(sum(recalls)/len(recalls),4),"mrr_at_3":round(sum(reciprocals)/len(reciprocals),4),
              "no_match_accuracy":round(sum(negative)/len(negative),4),
              "mean_retrieval_ms":round(sum(latencies)/len(latencies),3),
              "limitations":["Small synthetic development set, not an independent or real-paper benchmark.",
                              "Evaluates retrieved evidence, not generated-answer correctness or reproduction success.",
                              "No LLM, embeddings, GitHub network or GPU execution used."],"details":rows}
    out = ROOT / "docs/evaluation-results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))
    lines = ["# 离线检索评测结果", "", f"生成时间：{result['generated_at']}", "",
             "本报告来自脚本实际运行。使用 16 道合成开发集问题，其中 14 道有标注证据、2 道无匹配问题。", "",
             "| 指标 | 实测值 |", "| --- | --- |", f"| Recall@3 | {result['recall_at_3']:.2%} |",
             f"| MRR@3 | {result['mrr_at_3']:.4f} |", f"| 无匹配问题正确返回空结果 | {result['no_match_accuracy']:.2%} |",
             f"| 平均本地检索耗时 | {result['mean_retrieval_ms']:.3f} ms |", "",
             "这些数字仅检验小型合成资料上的证据定位，不是论文问答准确率、真实科研性能、复现成功率或大模型优势的证明。延迟随机器和负载变化。", "",
             "Recall@3 按预期的（资料名，页码）集合计算；同一来源同一页的重叠片段只算一次命中。MRR 取第一个正确证据位置的倒数。", "",
             "完整逐题结果见 evaluation-results.json。运行 `.venv/Scripts/python.exe scripts/evaluate.py` 可重现。", "",
             "后续评测：添加至少 5 篇有权使用的真实论文，独立标注问题与证据；划分开发/测试集；再比较裸 LLM、RAG、完整 Agent。人工评分应分别统计事实正确性、引用支持度与计划完整性。当前未进行该付费模型实验。"]
    (ROOT / "docs/evaluation-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()

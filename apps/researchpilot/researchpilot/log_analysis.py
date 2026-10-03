"""Bounded, deterministic extraction of explicitly logged metrics, without interpolation."""
import hashlib
import json
import math
import re

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .diagnostics import diagnose

MAX_POINTS = 2000
MAX_SERIES = 32
MAX_LINES = 50000
MAX_LINE_LENGTH = 4096
PARSER_VERSION = "1"
NUMBER = r"[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|nan|inf(?:inity)?)"
VALUE = re.compile(rf"({NUMBER})\s*(dB|%)?", re.I)
PAIR = re.compile(rf"(?<![\w/.-])([A-Za-z][\w/.-]{{0,79}})\s*[:=]\s*({NUMBER})\s*(dB|%)?(?![\w./%+-])", re.I)
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
METRICS = {"loss", "psnr", "ssim", "acc", "accuracy", "f1", "precision", "recall", "lr", "learning_rate", "mse", "mae"}
SPLITS = {"train": "train", "training": "train", "val": "val", "valid": "val", "validation": "val", "test": "test", "eval": "eval"}


class LogPointRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1, max_length=64)
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    point_id: str = Field(pattern=r"^[a-f0-9]{24}$")


def digest(value, length=64):
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def numeric(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    match = VALUE.fullmatch(str(value).strip())
    if not match:
        return None
    number = float(match[1])
    if not math.isfinite(number) or abs(number) > 1e100:
        return None
    return number, "dB" if (match[2] or "").lower() == "db" else match[2] or ""


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def metric_key(key, context):
    key = key.lower()
    if key in METRICS:
        return key, context
    prefix = re.fullmatch(r"(train|training|val|valid|validation|test|eval)[/_.-](.+)", key)
    if prefix and prefix[2] in METRICS:
        return prefix[2], SPLITS[prefix[1]]
    return None


def parse_log(text, checksum):
    series, lines, counts = {}, {}, {"invalid_values": 0, "long_lines": 0, "invalid_json": 0, "ambiguous": 0, "extra_series": 0}
    scanned, total, limited = 0, 0, False
    # Keep physical line order, including repeated steps; never deduplicate runs.
    physical_lines = text.splitlines()
    for number, raw in enumerate(physical_lines, 1):
        if number > MAX_LINES or total >= MAX_POINTS:
            limited = True
            break
        scanned = number
        if len(raw) > MAX_LINE_LENGTH:
            counts["long_lines"] += 1
            continue
        line = ANSI.sub("", raw).strip()
        context = ""
        pairs = []
        if line.startswith("{"):
            try:
                obj = json.loads(line, object_pairs_hook=unique_object)
                if not isinstance(obj, dict):
                    raise ValueError("not a JSON object")
                context = SPLITS.get(str(obj.get("split", obj.get("phase", ""))).lower(), "")
                for key, value in obj.items():
                    if isinstance(value, dict) and key.lower() in SPLITS:
                        pairs.extend((key + "/" + k, v) for k, v in value.items())
                    else:
                        pairs.append((key, value))
            except (ValueError, RecursionError):
                counts["invalid_json"] += 1
                continue
        else:
            prefix = re.match(r"\[?(train|training|val|valid|validation|test|eval)\]?\s", line, re.I)
            context = SPLITS.get(prefix[1].lower(), "") if prefix else ""
            pairs = [(m[1], m[2] + (m[3] or "")) for m in PAIR.finditer(line)]
        coordinates = {}
        for key in ("step", "epoch"):
            values = [numeric(v) for k, v in pairs if k.lower() == key]
            if len(values) == 1 and values[0] and not values[0][1] and 0 <= values[0][0] <= 1e12:
                coordinates[key] = values[0][0]
        candidates = []
        for key, value in pairs:
            identity = metric_key(key, context)
            if not identity:
                continue
            parsed = numeric(value)
            if parsed is None:
                counts["invalid_values"] += 1
                continue
            name, split = identity
            candidates.append((name, split, parsed[1], parsed[0], key))
        frequency = {}
        for name, split, unit, _, _ in candidates:
            # Repeated names on one line are ambiguous, even when units differ.
            frequency[name, split] = frequency.get((name, split), 0) + 1
        for name, split, unit, value, key in candidates:
            if total >= MAX_POINTS:
                limited = True
                break
            if frequency[name, split] > 1:
                counts["ambiguous"] += 1
                continue
            sid = digest(json.dumps([name, split, unit]), 16)
            if sid not in series:
                if len(series) >= MAX_SERIES:
                    counts["extra_series"] += 1
                    continue
                series[sid] = {"id": sid, "name": name, "split": split, "unit": unit, "points": []}
            point = {"id": digest(f"{PARSER_VERSION}|{checksum}|{number}|{key}", 24), "line": number, "value": value,
                     "step": coordinates.get("step"), "epoch": coordinates.get("epoch")}
            series[sid]["points"].append(point)
            lines[str(number)] = raw
            total += 1
    for item in series.values():
        points = item["points"]
        axis = next((a for a in ("step", "epoch") if all(p[a] is not None for p in points)), "line")
        item.update(axis=axis, count=len(points), last=points[-1]["id"],
                    minimum=min(points, key=lambda p: p["value"])["id"], maximum=max(points, key=lambda p: p["value"])["id"],
                    breaks=sum(b[axis] <= a[axis] for a, b in zip(points, points[1:])))
    warnings = []
    if limited:
        warnings.append(f"已达到最多 {MAX_POINTS} 个指标点或 {MAX_LINES} 行的分析上限，仅展示前部结果。")
    for key, message in (("invalid_values", "个非有限、过大或无法解析的指标值已跳过"), ("long_lines", "行超过 4096 字符，已跳过"),
                         ("invalid_json", "行 JSON 不符合单行对象格式或有重复键，已跳过"), ("ambiguous", "个同一行重复指标已跳过"), ("extra_series", "个超出 32 组序列上限的指标点已跳过")):
        if counts[key]:
            warnings.append(f"{counts[key]} {message}。")
    if any(s["breaks"] for s in series.values()):
        warnings.append("检测到重复或回退的 step / epoch，曲线在这些位置断开；可能包含多轮运行，不自动合并。")
    clean_text = "\n".join(ANSI.sub("", line) for line in physical_lines[:scanned])
    findings = diagnose(clean_text)
    for finding in findings:
        pos = clean_text.lower().find(finding["matched"].lower())
        finding["line"] = clean_text.count("\n", 0, max(pos, 0)) + 1
    return {"series": list(series.values()), "lines": lines, "warnings": warnings, "findings": findings,
            "point_count": total, "scanned_lines": scanned, "total_lines": len(physical_lines), "limited": limited,
            "parser_version": PARSER_VERSION}


class LogAnalysis:
    def __init__(self, db, imports):
        self.db, self.imports = db, imports

    def analyze(self, workspace, source_id, con=None):
        if con is None:
            with self.db.connect() as connection:
                connection.execute("BEGIN")
                return self.analyze(workspace, source_id, connection)
        row = con.execute("""SELECT s.id,s.name,s.kind,s.metadata,d.text,d.checksum FROM sources s
            LEFT JOIN log_documents d ON d.source_id=s.id WHERE s.workspace_id=? AND s.id=?""", (workspace, source_id)).fetchone()
        if not row:
            raise HTTPException(404, "日志不存在或不属于当前项目。")
        if row["kind"] != "log":
            raise HTTPException(422, "请选择日志类型的资料。")
        text, checksum = row["text"], row["checksum"]
        if text is None:
            original = json.loads(row["metadata"]).get("original_id")
            try:
                if not original:
                    raise OSError()
                with self.imports.path(original).open("r", encoding="utf-8-sig") as stream:
                    text = stream.read(1_000_001)
                if len(text) > 1_000_000:
                    raise ValueError()
            except (OSError, UnicodeError, ValueError):
                raise HTTPException(422, "此旧日志缺少完整文本，请重新导入同名日志以补齐；不会用重叠检索片段推测曲线。") from None
            checksum = digest(text)
        return {"source_id": row["id"], "source_name": row["name"], "checksum": checksum, **parse_log(text, checksum)}

    def resolve(self, workspace, origin, con, cache):
        if origin.source_id not in cache:
            cache[origin.source_id] = self.analyze(workspace, origin.source_id, con)
        analysis = cache[origin.source_id]
        if analysis["checksum"] != origin.checksum:
            raise HTTPException(409, "日志内容已变化，请重新分析并选择指标。")
        for series in analysis["series"]:
            for point in series["points"]:
                if point["id"] == origin.point_id:
                    return {"source_id": origin.source_id, "source_name": analysis["source_name"], "checksum": origin.checksum,
                            "point_id": point["id"], "name": series["name"], "unit": series["unit"], "split": series["split"],
                            "value": point["value"], "line": point["line"], "step": point["step"], "epoch": point["epoch"],
                            "text": analysis["lines"][str(point["line"])], "parser_version": PARSER_VERSION}
        raise HTTPException(422, "所选日志指标点不存在，请重新分析。")

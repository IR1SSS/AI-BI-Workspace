import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.llm.agent_skills import AgentSkill
from app.infrastructure.llm.llm_client import LLMMessage, OpenAICompatibleClient
from app.infrastructure.settings import settings


class ReportAgent:
    def __init__(self) -> None:
        self.catalog = DatasetCatalog()
        self.llm_client = OpenAICompatibleClient()

    def get_report(self, dataset_id: str, version_id: str) -> dict[str, Any] | None:
        path = self._report_path(dataset_id, version_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    async def generate(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        metadata = self.catalog.get_dataset(dataset_id, version_id)
        profile = self.catalog.get_profile(dataset_id, version_id)
        analysis = self.catalog.get_analysis(dataset_id, version_id)
        payload = await self._generate_report(metadata, profile, analysis)
        self._write_report(dataset_id, version_id, payload)
        return payload

    async def _generate_report(
        self,
        metadata: dict[str, Any],
        profile: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        fallback = self._fallback_report(metadata, profile, analysis)
        try:
            content = await self.llm_client.chat(self._messages(metadata, profile, analysis))
            parsed = self._parse_json(content)
            return self._normalize_report(parsed, fallback)
        except Exception as exc:
            fallback["source"] = "fallback"
            fallback["error"] = str(exc)
            return fallback

    def _messages(
        self,
        metadata: dict[str, Any],
        profile: dict[str, Any],
        analysis: dict[str, Any],
    ) -> list[LLMMessage]:
        compact_context = {
            "file_name": metadata.get("file_name"),
            "row_count": profile.get("row_count"),
            "column_count": profile.get("column_count"),
            "quality_issues": profile.get("quality_issues", [])[:8],
            "insights": analysis.get("insights", [])[:6],
            "cleaning_suggestions": analysis.get("cleaning_suggestions", [])[:6],
            "feature_suggestions": analysis.get("feature_suggestions", [])[:6],
        }
        schema = {
            "title": "string",
            "executive_summary": "string",
            "sections": [{"title": "string", "body": "string"}],
            "next_actions": ["string"],
        }
        skill = AgentSkill(
            name="ReportAgent",
            mission=(
                "Create a concise BI report that merges insights, data quality "
                "findings, and feature ideas."
            ),
            rules=[
                "Return only valid JSON matching the requested schema.",
                "Write in Chinese.",
                "Do not invent facts or exact values beyond the provided context.",
                "Mention uncertainty and required validation when a conclusion depends "
                "on missing domain context.",
                "Keep sections concise and action-oriented.",
            ],
            output_contract=(
                "JSON object with title, executive_summary, sections, and next_actions."
            ),
        )
        return [
            LLMMessage(
                role="system",
                content=skill.render(),
            ),
            LLMMessage(
                role="user",
                content=(
                    "Create an analysis report with this JSON shape:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                    "Context:\n"
                    f"{json.dumps(compact_context, ensure_ascii=False)}"
                ),
            ),
        ]

    def _fallback_report(
        self,
        metadata: dict[str, Any],
        profile: dict[str, Any],
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        insights = analysis.get("insights", [])
        cleaning = analysis.get("cleaning_suggestions", [])
        features = analysis.get("feature_suggestions", [])
        sections = [
            {
                "title": "核心发现",
                "body": self._join_items(insights, "detail") or "当前数据集已完成基础画像。",
            },
            {
                "title": "清洗建议",
                "body": self._join_items(cleaning, "rationale") or "暂未发现需要优先处理的清洗项。",
            },
            {
                "title": "扩展方向",
                "body": self._join_items(features, "rationale")
                or "可以结合业务目标继续设计派生指标。",
            },
        ]
        return {
            "title": f"{metadata.get('file_name', 'Dataset')} 分析报告",
            "executive_summary": (
                f"数据集包含 {profile.get('row_count')} 行、"
                f"{profile.get('column_count')} 列。"
            ),
            "sections": sections,
            "next_actions": [
                "确认关键业务指标",
                "审查高优先级数据质量问题",
                "基于报告结论完善仪表盘",
            ],
            "source": "deterministic",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _normalize_report(self, report: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        sections = report.get("sections")
        next_actions = report.get("next_actions")
        return {
            "title": str(report.get("title") or fallback["title"]),
            "executive_summary": str(
                report.get("executive_summary") or fallback["executive_summary"]
            ),
            "sections": sections
            if isinstance(sections, list) and sections
            else fallback["sections"],
            "next_actions": next_actions
            if isinstance(next_actions, list) and next_actions
            else fallback["next_actions"],
            "source": "llm",
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _parse_json(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`").removeprefix("json").strip()
        return json.loads(stripped)

    def _join_items(self, items: list[dict[str, Any]], body_key: str) -> str:
        parts = []
        for item in items[:4]:
            title = str(item.get("title") or "")
            body = str(item.get(body_key) or item.get("evidence") or "")
            if title or body:
                parts.append(f"{title}: {body}".strip(": "))
        return "\n".join(parts)

    def _write_report(self, dataset_id: str, version_id: str, payload: dict[str, Any]) -> None:
        path = self._report_path(dataset_id, version_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _report_path(self, dataset_id: str, version_id: str) -> Path:
        return settings.storage_root / "warehouse" / dataset_id / version_id / "report.json"

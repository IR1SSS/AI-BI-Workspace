import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from app.infrastructure.catalog.dataset_catalog import DatasetCatalog
from app.infrastructure.chat.chat_history_store import ChatHistoryStore
from app.infrastructure.llm.agent_skills import AgentSkill
from app.infrastructure.llm.llm_client import LLMMessage, OpenAICompatibleClient
from app.infrastructure.query.duckdb_query_engine import DuckDBQueryEngine


class ChatBIService:
    def __init__(self) -> None:
        self.catalog = DatasetCatalog()
        self.llm_client = OpenAICompatibleClient()
        self.query_engine = DuckDBQueryEngine()
        self.history_store = ChatHistoryStore()

    def history(self, dataset_id: str, version_id: str) -> list[dict[str, Any]]:
        self.catalog.get_dataset(dataset_id, version_id)
        return self.history_store.list_messages(dataset_id, version_id)

    def delete_history(self, dataset_id: str, version_id: str) -> dict[str, bool]:
        self.catalog.get_dataset(dataset_id, version_id)
        self.history_store.delete_messages(dataset_id, version_id)
        return {"deleted": True}

    async def suggested_questions(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        context = self._build_context(dataset_id, version_id)
        fallback = self._fallback_suggestions(context)

        try:
            content = await self.llm_client.chat(self._suggestion_messages(context))
            parsed = self._parse_json(content)
            suggestions = self._normalize_suggestions(parsed, fallback)
            return {"source": "llm", "suggestions": suggestions}
        except Exception as exc:
            return {
                "source": "profile_fallback",
                "suggestions": fallback,
                "error": str(exc),
            }

    async def ask(self, dataset_id: str, version_id: str, question: str) -> dict[str, Any]:
        response = await self.answer(dataset_id, version_id, question)
        messages = self.history_store.append_exchange(dataset_id, version_id, question, response)
        response["messages"] = messages
        return response

    async def answer(self, dataset_id: str, version_id: str, question: str) -> dict[str, Any]:
        context = self._build_context(dataset_id, version_id)
        sql_plan = await self._generate_sql(question, context)
        sql = str(sql_plan.get("sql") or "").strip()

        rows: list[dict[str, Any]] = []
        query_error = ""
        if sql:
            try:
                rows = self.query_engine.query_parquet(
                    Path(context["metadata"]["parquet_path"]),
                    sql,
                    limit=80,
                )
            except Exception as exc:
                query_error = str(exc)

        answer = await self._summarize_answer(question, context, sql, rows, query_error)
        return {
            "answer": answer,
            "sql": sql if rows else "",
            "rows": rows[:20],
            "source": "llm_sql" if rows else "llm_profile",
            "error": query_error,
        }

    def _build_context(self, dataset_id: str, version_id: str) -> dict[str, Any]:
        metadata = self.catalog.get_dataset(dataset_id, version_id)
        profile = self.catalog.get_profile(dataset_id, version_id)
        analysis = self.catalog.get_analysis(dataset_id, version_id)
        sample = self._sample_rows(Path(metadata["parquet_path"]))
        columns = [
            {
                "name": column["name"],
                "data_type": column["data_type"],
                "is_numeric": column["is_numeric"],
                "is_datetime": column["is_datetime"],
                "unique_count": column["unique_count"],
                "sample_values": column["sample_values"][:3],
            }
            for column in profile["columns"]
            if not column.get("is_probable_index")
        ]
        return {
            "metadata": metadata,
            "profile": {
                "row_count": profile["row_count"],
                "column_count": profile["column_count"],
                "columns": columns,
                "quality_issues": profile.get("quality_issues", [])[:8],
            },
            "analysis": {
                "insights": analysis.get("insights", [])[:5],
                "cleaning_suggestions": analysis.get("cleaning_suggestions", [])[:5],
                "feature_suggestions": analysis.get("feature_suggestions", [])[:5],
            },
            "sample_rows": sample,
        }

    def _sample_rows(self, parquet_path: Path) -> list[dict[str, Any]]:
        dataframe = pd.read_parquet(parquet_path).head(8)
        safe = dataframe.astype(object).where(pd.notnull(dataframe), None)
        return json.loads(safe.to_json(orient="records", date_format="iso", force_ascii=False))

    async def _generate_sql(self, question: str, context: dict[str, Any]) -> dict[str, Any]:
        schema = {"sql": "SELECT ... FROM dataset WHERE ...", "reason": "string"}
        prompt_context = {
            "file_name": context["metadata"]["file_name"],
            "row_count": context["profile"]["row_count"],
            "columns": context["profile"]["columns"],
            "sample_rows": context["sample_rows"],
        }
        skill = AgentSkill(
            name="SQLBotQueryPlanner",
            mission="Translate a user BI question into safe DuckDB SQL over a view named dataset.",
            rules=[
                "Return only valid JSON.",
                "Only SELECT or WITH queries are allowed.",
                "Use double quotes around every column name.",
                "Use only columns listed in the dataset context.",
                "Never use read_parquet, file functions, DDL, DML, COPY, PRAGMA, INSTALL, or LOAD.",
                "If the question cannot be answered with SQL, return an empty sql string "
                "and explain why in reason.",
            ],
            output_contract='JSON object: {"sql": "...", "reason": "..."}.',
        )
        messages = [
            LLMMessage(
                role="system",
                content=skill.render(),
            ),
            LLMMessage(
                role="user",
                content=(
                    "Question:\n"
                    f"{question}\n\n"
                    "Return this exact JSON shape:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                    "Dataset context:\n"
                    f"{json.dumps(prompt_context, ensure_ascii=False)}"
                ),
            ),
        ]
        try:
            content = await self.llm_client.chat(messages)
            parsed = self._parse_json(content)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
        return {}

    async def _summarize_answer(
        self,
        question: str,
        context: dict[str, Any],
        sql: str,
        rows: list[dict[str, Any]],
        query_error: str,
    ) -> str:
        result_context = {
            "file_name": context["metadata"]["file_name"],
            "profile": context["profile"],
            "analysis": context["analysis"],
            "sql": sql,
            "query_rows": rows[:20],
            "query_error": query_error,
        }
        skill = AgentSkill(
            name="SQLBotAnswerWriter",
            mission=(
                "Answer dataset questions in Chinese using query results, profile context, "
                "and visible limitations."
            ),
            rules=[
                "Use query_rows when available and cite the calculation basis briefly.",
                "If SQL failed, answer from the profile and state the limitation briefly.",
                "Do not fabricate exact values that are not in the provided context.",
                "Use concise Markdown with tables or bullets when helpful.",
            ],
            output_contract="Markdown text in Chinese.",
        )
        messages = [
            LLMMessage(
                role="system",
                content=skill.render(),
            ),
            LLMMessage(
                role="user",
                content=(
                    "User question:\n"
                    f"{question}\n\n"
                    "Available context:\n"
                    f"{json.dumps(result_context, ensure_ascii=False)}"
                ),
            ),
        ]
        try:
            return await self.llm_client.chat(messages)
        except Exception as exc:
            row_count = context["profile"]["row_count"]
            column_count = context["profile"]["column_count"]
            if query_error:
                return (
                    f"暂时无法执行查询：{query_error}。"
                    f"可用的数据概要显示共有 {row_count} 行、{column_count} 列。"
                )
            return f"暂时无法调用 LLM：{exc}。当前数据集共有 {row_count} 行、{column_count} 列。"

    def _suggestion_messages(self, context: dict[str, Any]) -> list[LLMMessage]:
        schema = {"suggestions": ["💡 string", "📈 string", "🔍 string"]}
        prompt_context = {
            "file_name": context["metadata"]["file_name"],
            "row_count": context["profile"]["row_count"],
            "columns": context["profile"]["columns"],
            "quality_issues": context["profile"]["quality_issues"],
            "insights": context["analysis"]["insights"],
            "sample_rows": context["sample_rows"][:5],
        }
        skill = AgentSkill(
            name="SQLBotQuestionCoach",
            mission="Generate dataset-specific starter questions for a Chinese BI chat assistant.",
            rules=[
                "Return only valid JSON.",
                "Return exactly three distinct suggestions in Chinese.",
                "Each suggestion must be answerable from the provided dataset context.",
                "Mention relevant column names or business concepts from the dataset "
                "when possible.",
                "Use one concise emoji prefix per suggestion.",
                "Avoid generic fixed examples that do not match the dataset.",
            ],
            output_contract='JSON object: {"suggestions": ["...", "...", "..."]}.',
        )
        return [
            LLMMessage(role="system", content=skill.render()),
            LLMMessage(
                role="user",
                content=(
                    "Return this exact JSON shape:\n"
                    f"{json.dumps(schema, ensure_ascii=False)}\n\n"
                    "Dataset context:\n"
                    f"{json.dumps(prompt_context, ensure_ascii=False)}"
                ),
            ),
        ]

    def _normalize_suggestions(self, parsed: Any, fallback: list[str]) -> list[str]:
        if not isinstance(parsed, dict):
            return fallback

        raw_suggestions = parsed.get("suggestions")
        if not isinstance(raw_suggestions, list):
            return fallback

        suggestions: list[str] = []
        for item in raw_suggestions:
            if isinstance(item, dict):
                item = item.get("question") or item.get("text")
            if not isinstance(item, str):
                continue

            suggestion = " ".join(item.strip().split())
            if suggestion and suggestion not in suggestions:
                suggestions.append(suggestion[:90])

        for suggestion in fallback:
            if len(suggestions) >= 3:
                break
            if suggestion not in suggestions:
                suggestions.append(suggestion)

        return suggestions[:3]

    def _fallback_suggestions(self, context: dict[str, Any]) -> list[str]:
        columns = context["profile"]["columns"]
        numeric_columns = [column["name"] for column in columns if column.get("is_numeric")]
        time_columns = [column["name"] for column in columns if column.get("is_datetime")]
        dimension_columns = [
            column["name"]
            for column in columns
            if not column.get("is_numeric") and not column.get("is_datetime")
        ]
        quality_issues = context["profile"].get("quality_issues", [])

        metric = numeric_columns[0] if numeric_columns else "关键指标"
        dimension = dimension_columns[0] if dimension_columns else "主要维度"
        time_column = time_columns[0] if time_columns else ""

        candidates = []
        if dimension_columns and numeric_columns:
            candidates.append(f"💡 哪个{dimension}的{metric}最高？")
            candidates.append(f"📊 按{dimension}拆分，{metric}有哪些差异？")
        if time_column and numeric_columns:
            candidates.append(f"📈 {metric}随{time_column}有什么趋势？")
        if len(numeric_columns) >= 2:
            candidates.append(f"🔗 {numeric_columns[0]}和{numeric_columns[1]}是否相关？")
        if quality_issues:
            candidates.append("🔍 哪些数据质量问题需要优先处理？")
        if numeric_columns:
            candidates.append(f"⚠️ {metric}是否存在异常值？")
        if dimension_columns:
            candidates.append(f"🧭 {dimension}的分布有什么特点？")
        candidates.append("✨ 这个数据集有哪些关键洞察？")

        suggestions: list[str] = []
        for candidate in candidates:
            if candidate not in suggestions:
                suggestions.append(candidate)
            if len(suggestions) == 3:
                break
        return suggestions

    def _parse_json(self, content: str) -> Any:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()

        match = re.search(r"\{.*\}", stripped, re.DOTALL)
        if not match:
            raise ValueError("LLM response did not contain JSON")
        return json.loads(match.group(0))

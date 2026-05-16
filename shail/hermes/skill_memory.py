"""
Skill Memory

In-memory skill storage and retrieval for MVP.
Connects to RAG in production.
"""

import uuid
import logging
from typing import Dict, List, Optional

from shail.hermes.types import HermesSkill, ExecutionTrace, ExecutionStatus


logger = logging.getLogger(__name__)


class SkillMemory:
    """
    In-memory skill storage for MVP.

    Features:
    - Store/retrieve skills
    - Search skills by keyword
    - Generate skills from execution traces
    - Track usage statistics
    """

    def __init__(self):
        self._skills: Dict[str, HermesSkill] = {}
        self._traces: Dict[str, ExecutionTrace] = {}

    def store_skill(self, skill: HermesSkill) -> None:
        """Store a skill."""
        self._skills[skill.skill_id] = skill
        logger.info(f"Stored skill: {skill.skill_id} - {skill.name}")

    def get_skill(self, skill_id: str) -> Optional[HermesSkill]:
        """Get a specific skill by ID."""
        return self._skills.get(skill_id)

    def get_all_skills(self) -> List[HermesSkill]:
        """Get all stored skills."""
        return list(self._skills.values())

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill by ID."""
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False

    def search_skills(self, query: str) -> List[HermesSkill]:
        """
        Search skills by keyword (simple matching for MVP).

        In production, this would use RAG embeddings.
        """
        query_lower = query.lower()
        results = []

        for skill in self._skills.values():
            # Search in name, description, and tags
            search_text = " ".join([
                skill.name.lower(),
                (skill.description or "").lower(),
                " ".join(skill.tags),
            ])

            if query_lower in search_text:
                results.append(skill)

        # Sort by success rate (highest first)
        results.sort(key=lambda s: s.success_rate, reverse=True)

        return results

    def update_skill_stats(self, skill_id: str, success: bool) -> None:
        """Update skill usage statistics."""
        skill = self._skills.get(skill_id)
        if not skill:
            return

        skill.execution_count += 1

        # Update success rate with exponential moving average
        if success:
            skill.success_rate = 0.9 * skill.success_rate + 0.1 * 1.0
        else:
            skill.success_rate = 0.9 * skill.success_rate + 0.1 * 0.0

        logger.debug(f"Updated skill {skill_id}: count={skill.execution_count}, rate={skill.success_rate:.2f}")

    def generate_skill_from_trace(self, trace: ExecutionTrace) -> Optional[HermesSkill]:
        """
        Generate a skill from a successful execution trace.

        Only generates skills for traces that:
        - Completed successfully
        - Took more than 2 seconds (worth skillifying)
        """
        if trace.status != ExecutionStatus.COMPLETED:
            return None

        if trace.execution_time_ms < 2000:  # Less than 2 seconds
            logger.debug(f"Trace too fast to skillify: {trace.execution_time_ms}ms")
            return None

        # Create skill from trace
        skill_id = f"skill_{uuid.uuid4().hex[:8]}"

        # Build a simple prompt template from the task
        prompt_template = f"""Task: {{task}}

Context: {{context}}

Execute the following steps to complete the task."""

        skill = HermesSkill(
            skill_id=skill_id,
            name=f"Auto-generated: {trace.task[:40]}",
            prompt_template=prompt_template,
            description=f"Generated from trace {trace.trace_id}",
            tags=["auto-generated", "from-trace"],
        )

        logger.info(f"Generated skill from trace: {skill.skill_id}")
        return skill

    def store_trace(self, trace: ExecutionTrace) -> None:
        """Store an execution trace."""
        self._traces[trace.trace_id] = trace
        logger.debug(f"Stored trace: {trace.trace_id}")

    def get_trace(self, trace_id: str) -> Optional[ExecutionTrace]:
        """Get a specific trace by ID."""
        return self._traces.get(trace_id)

    def get_traces(
        self,
        status: Optional[ExecutionStatus] = None,
        limit: int = 100,
    ) -> List[ExecutionTrace]:
        """Get traces, optionally filtered by status."""
        traces = list(self._traces.values())

        if status:
            traces = [t for t in traces if t.status == status]

        # Sort by creation (most recent first)
        traces.sort(key=lambda t: t.trace_id, reverse=True)

        return traces[:limit]

    def get_failed_traces(self, limit: int = 50) -> List[ExecutionTrace]:
        """Get failed traces for analysis."""
        return self.get_traces(status=ExecutionStatus.FAILED, limit=limit)

    def get_successful_traces(self, limit: int = 50) -> List[ExecutionTrace]:
        """Get successful traces."""
        return self.get_traces(status=ExecutionStatus.COMPLETED, limit=limit)

    def clear(self) -> None:
        """Clear all skills and traces (for testing)."""
        self._skills.clear()
        self._traces.clear()
        logger.info("Cleared all skills and traces")

    def get_stats(self) -> Dict:
        """Get memory statistics."""
        return {
            "total_skills": len(self._skills),
            "total_traces": len(self._traces),
            "successful_traces": len([t for t in self._traces.values() if t.status == ExecutionStatus.COMPLETED]),
            "failed_traces": len([t for t in self._traces.values() if t.status == ExecutionStatus.FAILED]),
            "avg_skill_success_rate": sum(s.success_rate for s in self._skills.values()) / max(len(self._skills), 1),
        }


# Singleton instance
_skill_memory: Optional[SkillMemory] = None


def get_skill_memory() -> SkillMemory:
    """Get singleton skill memory instance."""
    global _skill_memory
    if _skill_memory is None:
        _skill_memory = SkillMemory()
    return _skill_memory


def reset_skill_memory() -> SkillMemory:
    """Reset skill memory singleton (for testing)."""
    global _skill_memory
    _skill_memory = SkillMemory()
    return _skill_memory
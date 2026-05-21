"""
Basic Reflection

Stores failure/success info for later analysis.
MVP version - just stores data, no optimization yet.
"""

import logging
from typing import Dict, Any, Optional

from shail.hermes.types import ExecutionTrace, ExecutionStatus, HermesSkill
from shail.hermes.skill_memory import SkillMemory


logger = logging.getLogger(__name__)


class Reflection:
    """
    Basic reflection for MVP.

    Features:
    - Store execution traces
    - Analyze successful traces for skill generation
    - Track failure patterns
    - Generate summaries

    In production, this would include:
    - Prompt optimization
    - Tool strategy improvements
    - Automatic skill refinement
    """

    def __init__(self, skill_memory: SkillMemory):
        self.skill_memory = skill_memory

    def reflect(self, trace: ExecutionTrace) -> Dict[str, Any]:
        """
        Analyze an execution trace and take appropriate action.

        Returns a reflection result with:
        - trace_id
        - status
        - skill_generated (if any)
        - error_analyzed (if any)
        """
        result = {
            "trace_id": trace.trace_id,
            "status": trace.status.value,
            "skill_generated": False,
            "skill_refined": False,
            "tool_discovered": False,
            "error_analyzed": False,
            "insights": [],
        }

        # Store trace for later analysis (this now also ingests to VectorStore if successful)
        self.skill_memory.store_trace(trace)

        # Autonomous Tool Discovery Check
        if trace.status == ExecutionStatus.COMPLETED and "sandbox" in str(trace.result).lower():
            result["tool_discovered"] = True
            result["insights"].append("Potential new tool discovered from sandbox execution")
            logger.info(f"Reflection: Potential new tool discovered from trace {trace.trace_id}")

        if trace.status == ExecutionStatus.COMPLETED:
            result["insights"].append("Task completed successfully")

            # Check if we should generate a skill
            if trace.execution_time_ms > 2000 and not getattr(trace, 'skill_used', None):
                skill = self.skill_memory.generate_skill_from_trace(trace)
                if skill:
                    self.skill_memory.store_skill(skill)
                    result["skill_generated"] = True
                    result["insights"].append(f"Generated skill: {skill.skill_id}")
                    logger.info(f"Reflection: Generated skill from trace {trace.trace_id}")
            elif getattr(trace, 'skill_used', None):
                result["insights"].append(f"Successfully used skill: {trace.skill_used}")

        elif trace.status == ExecutionStatus.FAILED:
            result["insights"].append(f"Task failed: {trace.error}")
            result["error_analyzed"] = True

            # Autonomous Skill Refinement
            skill_used = getattr(trace, 'skill_used', None)
            if skill_used:
                skill = self.skill_memory.get_skill(skill_used)
                if skill:
                    self._refine_skill(skill, trace)
                    result["skill_refined"] = True
                    result["insights"].append(f"Refined failing skill: {skill.skill_id}")
                    logger.info(f"Reflection: Refined skill {skill.skill_id} due to failure")

            # Analyze error for patterns (MVP - just log)
            self._analyze_error(trace)

        return result

    def _refine_skill(self, skill: HermesSkill, trace: ExecutionTrace) -> None:
        """Modify an existing skill based on failure feedback."""
        # Simple refinement logic: Append warning to prompt template
        if "AVOID PREVIOUS ERROR:" not in skill.prompt_template:
            skill.prompt_template += f"\n\nAVOID PREVIOUS ERROR: {trace.error}"
            self.skill_memory.store_skill(skill)

    def _analyze_error(self, trace: ExecutionTrace) -> None:
        """Analyze error patterns (MVP - basic logging)."""
        if not trace.error:
            return

        error_lower = trace.error.lower()

        # Simple pattern detection
        if "timeout" in error_lower:
            logger.info(f"Pattern detected: timeout error in trace {trace.trace_id}")
        elif "rate_limit" in error_lower:
            logger.info(f"Pattern detected: rate limit in trace {trace.trace_id}")
        elif "connection" in error_lower:
            logger.info(f"Pattern detected: connection error in trace {trace.trace_id}")
        else:
            logger.debug(f"Error in trace {trace.trace_id}: {trace.error}")

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all reflections."""
        stats = self.skill_memory.get_stats()

        return {
            "total_traces": stats["total_traces"],
            "successful": stats["successful_traces"],
            "failed": stats["failed_traces"],
            "skills_generated": stats["total_skills"],
            "avg_success_rate": stats["avg_skill_success_rate"],
        }

    def analyze_failures(self) -> Dict[str, Any]:
        """Analyze all failures for patterns."""
        failed_traces = self.skill_memory.get_failed_traces()

        if not failed_traces:
            return {
                "total_failures": 0,
                "patterns": [],
            }

        # Count error types
        error_counts: Dict[str, int] = {}

        for trace in failed_traces:
            if trace.error:
                # Simple categorization
                error_lower = trace.error.lower()
                if "timeout" in error_lower:
                    error_type = "timeout"
                elif "rate_limit" in error_lower:
                    error_type = "rate_limit"
                elif "connection" in error_lower:
                    error_type = "connection"
                elif "permission" in error_lower:
                    error_type = "permission"
                else:
                    error_type = "other"

                error_counts[error_type] = error_counts.get(error_type, 0) + 1

        return {
            "total_failures": len(failed_traces),
            "error_types": error_counts,
            "failure_rate": len(failed_traces) / max(self.skill_memory.get_stats()["total_traces"], 1),
        }

    def suggest_improvements(self) -> Dict[str, Any]:
        """Suggest improvements based on analysis."""
        suggestions = []

        # Analyze failures
        failure_analysis = self.analyze_failures()

        if failure_analysis["failure_rate"] > 0.3:
            suggestions.append({
                "type": "high_failure_rate",
                "message": f"Failure rate is {failure_analysis['failure_rate']:.1%}, consider adding retries",
            })

        if "timeout" in failure_analysis.get("error_types", {}):
            suggestions.append({
                "type": "timeout_errors",
                "message": "Timeouts detected, consider increasing timeout values",
            })

        if "rate_limit" in failure_analysis.get("error_types", {}):
            suggestions.append({
                "type": "rate_limiting",
                "message": "Rate limits detected, consider adding request throttling",
            })

        # Check skill success rates
        stats = self.skill_memory.get_stats()
        if stats["total_skills"] > 0 and stats["avg_skill_success_rate"] < 0.7:
            suggestions.append({
                "type": "low_skill_success",
                "message": f"Average skill success rate is {stats['avg_skill_success_rate']:.1%}, consider improving skill templates",
            })

        return {
            "suggestions": suggestions,
            "failure_analysis": failure_analysis,
        }


# Singleton instance
_reflection: Optional[Reflection] = None


def get_reflection(skill_memory: Optional[SkillMemory] = None) -> Reflection:
    """Get singleton reflection instance."""
    global _reflection
    if _reflection is None:
        from shail.hermes.skill_memory import get_skill_memory
        memory = skill_memory or get_skill_memory()
        _reflection = Reflection(memory)
    return _reflection


def reset_reflection(skill_memory: Optional[SkillMemory] = None) -> Reflection:
    """Reset reflection singleton (for testing)."""
    global _reflection
    from shail.hermes.skill_memory import get_skill_memory
    memory = skill_memory or get_skill_memory()
    _reflection = Reflection(memory)
    return _reflection
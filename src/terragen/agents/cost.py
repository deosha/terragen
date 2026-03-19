"""Cost estimation agent for running infracost analysis."""

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from rich.console import Console

from terragen.agents.base import (
    AgentResult,
    AgentStatus,
    BaseAgent,
    CostBreakdown,
)
from terragen.agents.context import PipelineContext
from terragen.agents.visualization import print_cost_summary


class CostEstimationAgent(BaseAgent):
    """Agent that estimates infrastructure costs using Infracost.

    Analyzes Terraform code and provides cost estimates for
    the planned infrastructure resources.
    """

    name = "CostEstimationAgent"
    description = "Estimates infrastructure costs using Infracost"
    is_gate = False  # Cost estimation doesn't block pipeline

    def __init__(
        self, console: Optional[Console] = None, log_callback: Optional[Any] = None
    ):
        """Initialize the cost estimation agent."""
        super().__init__(console, log_callback)
        self.timeout = 120  # seconds

    async def execute(self, context: PipelineContext) -> AgentResult:
        """Execute cost estimation.

        Args:
            context: Pipeline context with output directory.

        Returns:
            AgentResult with cost breakdown.
        """
        self._status = AgentStatus.RUNNING

        output_dir = context.output_dir
        if not output_dir.exists():
            self._log_error(f"Output directory does not exist: {output_dir}")
            return AgentResult(
                status=AgentStatus.FAILED,
                errors=["Output directory does not exist"],
            )

        # Check if infracost is installed
        if not await self._check_infracost_installed():
            self._log_warning("infracost not installed, skipping cost estimation")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "infracost not installed"},
            )

        # Check if INFRACOST_API_KEY is set
        import os

        if not os.environ.get("INFRACOST_API_KEY"):
            self._log_warning("INFRACOST_API_KEY not set, skipping cost estimation")
            self._status = AgentStatus.SKIPPED
            return AgentResult(
                status=AgentStatus.SKIPPED,
                data={"reason": "INFRACOST_API_KEY not set"},
            )

        self._log_info("Running Infracost analysis...")
        costs, total_monthly, total_yearly = await self._run_infracost(output_dir)

        # Update context
        context.cost_breakdown = costs
        context.total_monthly_cost = total_monthly
        context.total_yearly_cost = total_yearly
        context.cost_estimated = True

        if costs:
            print_cost_summary(self.console, costs, total_monthly, total_yearly)
            self._log_success(f"Cost estimation complete: ${total_monthly:,.2f}/month")
        else:
            self._log_warning("No cost data returned from Infracost")

        self._status = AgentStatus.SUCCESS
        return AgentResult(
            status=AgentStatus.SUCCESS,
            data={
                "costs": [self._cost_to_dict(c) for c in costs],
                "total_monthly": total_monthly,
                "total_yearly": total_yearly,
            },
        )

    async def _check_infracost_installed(self) -> bool:
        """Check if infracost is installed.

        Returns:
            True if infracost is available.
        """
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["infracost", "--version"],
                    capture_output=True,
                    timeout=10,
                ),
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    async def _run_infracost(
        self, output_dir: Path
    ) -> tuple[list[CostBreakdown], float, float]:
        """Run infracost and parse results.

        Args:
            output_dir: Directory containing Terraform files.

        Returns:
            Tuple of (cost breakdowns, total monthly, total yearly).
        """
        costs = []
        total_monthly = 0.0
        total_yearly = 0.0

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "infracost",
                        "breakdown",
                        "--path",
                        str(output_dir),
                        "--format",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                ),
            )

            if result.stdout:
                try:
                    data = json.loads(result.stdout)
                    costs, total_monthly, total_yearly = self._parse_infracost_output(
                        data
                    )
                except json.JSONDecodeError:
                    self._log_warning("Failed to parse infracost JSON output")
                    if result.stderr:
                        self._log_warning(f"Infracost stderr: {result.stderr[:200]}")

        except subprocess.TimeoutExpired:
            self._log_error("infracost analysis timed out")
        except FileNotFoundError:
            self._log_warning("infracost not found")
        except Exception as e:
            self._log_error(f"Error running infracost: {str(e)}")

        return costs, total_monthly, total_yearly

    def _parse_infracost_output(
        self, data: dict[str, Any]
    ) -> tuple[list[CostBreakdown], float, float]:
        """Parse infracost JSON output into CostBreakdown objects.

        Args:
            data: Parsed JSON output from infracost.

        Returns:
            Tuple of (cost breakdowns, total monthly, total yearly).
        """
        costs = []
        total_monthly = 0.0

        # Get total from summary
        total_monthly_cost = data.get("totalMonthlyCost")
        if total_monthly_cost:
            try:
                total_monthly = float(total_monthly_cost)
            except (ValueError, TypeError):
                pass

        # Parse projects and resources
        for project in data.get("projects", []):
            breakdown = project.get("breakdown", {})

            for resource in breakdown.get("resources", []):
                name = resource.get("name", "Unknown")
                resource_type = self._extract_resource_type(name)

                monthly = 0.0
                monthly_cost = resource.get("monthlyCost")
                if monthly_cost:
                    try:
                        monthly = float(monthly_cost)
                    except (ValueError, TypeError):
                        pass

                hourly = 0.0
                hourly_cost = resource.get("hourlyCost")
                if hourly_cost:
                    try:
                        hourly = float(hourly_cost)
                    except (ValueError, TypeError):
                        pass

                # Only add resources with non-zero cost
                if monthly > 0:
                    costs.append(
                        CostBreakdown(
                            resource_name=self._simplify_resource_name(name),
                            resource_type=resource_type,
                            monthly_cost=monthly,
                            yearly_cost=monthly * 12,
                            hourly_cost=hourly,
                        )
                    )

        # Calculate total yearly
        total_yearly = total_monthly * 12

        # Sort by monthly cost descending
        costs.sort(key=lambda x: x.monthly_cost, reverse=True)

        return costs, total_monthly, total_yearly

    def _extract_resource_type(self, name: str) -> str:
        """Extract resource type from Terraform resource name.

        Args:
            name: Full resource name (e.g., aws_instance.web_server).

        Returns:
            Simplified resource type.
        """
        # Map common Terraform resource types to friendly names
        type_mapping = {
            "aws_instance": "EC2",
            "aws_db_instance": "RDS",
            "aws_s3_bucket": "S3",
            "aws_lambda_function": "Lambda",
            "aws_ecs_service": "ECS",
            "aws_eks_cluster": "EKS",
            "aws_elasticache": "ElastiCache",
            "aws_elb": "ELB",
            "aws_alb": "ALB",
            "aws_nat_gateway": "NAT Gateway",
            "aws_ebs_volume": "EBS",
            "aws_rds_cluster": "Aurora",
            "azurerm_virtual_machine": "VM",
            "azurerm_sql_database": "SQL DB",
            "azurerm_storage_account": "Storage",
            "google_compute_instance": "Compute",
            "google_sql_database_instance": "Cloud SQL",
            "google_storage_bucket": "GCS",
        }

        # Try to match resource type from name
        for tf_type, friendly_name in type_mapping.items():
            if name.startswith(tf_type):
                return friendly_name

        # Fallback: extract type from name
        parts = name.split(".")
        if parts:
            resource_type = parts[0]
            # Clean up provider prefix
            for prefix in ["aws_", "azurerm_", "google_"]:
                if resource_type.startswith(prefix):
                    resource_type = resource_type[len(prefix) :]
                    break
            return resource_type.replace("_", " ").title()

        return "Resource"

    def _simplify_resource_name(self, name: str) -> str:
        """Simplify resource name for display.

        Args:
            name: Full resource name (e.g., module.main.aws_instance.web[0]).

        Returns:
            Simplified display name (e.g., aws_instance.web[0]).
        """
        # Remove "module.xxx." prefix if present
        if name.startswith("module."):
            parts = name.split(".", 2)
            if len(parts) >= 3:
                name = parts[2]  # Get everything after "module.xxx."

        # Keep the full resource type and name (e.g., aws_instance.web[0])
        return name

    def _cost_to_dict(self, cost: CostBreakdown) -> dict[str, Any]:
        """Convert CostBreakdown to dictionary.

        Args:
            cost: CostBreakdown to convert.

        Returns:
            Dictionary representation.
        """
        return {
            "resource_name": cost.resource_name,
            "resource_type": cost.resource_type,
            "monthly_cost": cost.monthly_cost,
            "yearly_cost": cost.yearly_cost,
            "hourly_cost": cost.hourly_cost,
            "unit": cost.unit,
        }
